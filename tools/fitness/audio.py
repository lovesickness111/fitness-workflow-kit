"""Narration per script segment, frame-aligned padding and sentence beats.

Genmax is asynchronous: a task id is checkpointed before polling, so an
interrupted run resumes the same task. A submit whose outcome is unknown is
reconciled against Genmax history; it is never sent again automatically.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import channel as channel_profile
from . import providers
from .common import FitnessError, file_hash, frames, now, probe, run


SILENCE = {"noise": "-38dB", "duration": 0.24}


def _pending(project) -> dict:
    return project.state.setdefault("audio_tasks", {})


def _finish(project, segment: dict, fingerprint: str, source: Path, provider: str, extra: dict) -> dict:
    _, _, fps = project.size
    gap = float(project.channel.get("scene_gap_seconds", 0.35))
    with tempfile.TemporaryDirectory() as tmp:
        speech = Path(tmp) / "speech.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *extra.get("input_args", []), "-i", source,
             "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", speech])
        speech_seconds = probe(speech)["duration"]
        total = frames(speech_seconds + gap, fps) / fps
        output = project.path(f"audio/{segment['id']}-{fingerprint[:12]}.wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", speech, "-af", f"apad=whole_dur={total:.6f}",
             "-t", f"{total:.6f}", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", output])
    record = {"input_sha256": fingerprint, "path": project.rel(output), "sha256": file_hash(output),
              "seconds": total, "speech_seconds": speech_seconds, "provider": provider, "created_at": now()}
    for key in ("task_id", "credits"):
        if extra.get(key) is not None:
            record[key] = extra[key]
    project.state["audio"][segment["id"]] = record
    _pending(project).pop(segment["id"], None)
    project.save()
    return record


def _genmax_one(project, segment: dict, fingerprint: str, voice: dict, wait_seconds: int) -> dict:
    pending = _pending(project).get(segment["id"])
    if pending and pending.get("input_sha256") != fingerprint:
        if pending.get("status") == "submitting":
            raise FitnessError(f"{segment['id']}: an earlier submit has an unknown outcome; run `audio --reconcile` first")
        pending = None  # an older text/voice; its finished task is simply not used
    if pending and pending.get("status") == "submitting":
        raise FitnessError(f"{segment['id']}: the last submit has an unknown outcome; run `audio --reconcile` before generating again")
    if not pending:
        _pending(project)[segment["id"]] = {"input_sha256": fingerprint, "status": "submitting", "text": segment["text"], "at": now()}
        project.save()
        try:
            task_id = providers.genmax_submit(segment["text"], voice)
        except providers.UncertainOutcome:
            raise
        except FitnessError:
            _pending(project).pop(segment["id"], None)  # rejected with an HTTP error: nothing was queued
            project.save()
            raise
        pending = {"input_sha256": fingerprint, "status": "submitted", "task_id": task_id, "text": segment["text"], "at": now()}
        _pending(project)[segment["id"]] = pending
        project.save()
    task = providers.genmax_wait(pending["task_id"], wait_seconds=wait_seconds)
    url = (task.get("result") or {}).get("audio_url")
    if not url:
        raise FitnessError(f"Genmax task {pending['task_id']} completed without an audio_url")
    raw = project.path(f"audio/raw/{segment['id']}-{fingerprint[:12]}.mp3")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(providers.genmax_download(url))
    return _finish(project, segment, fingerprint, raw, "genmax", {"task_id": pending["task_id"], "credits": task.get("credits_deducted")})


def _gemini_one(project, segment: dict, fingerprint: str, voice: dict) -> dict:
    style = " ".join(part for part in (voice.get("style", ""), segment.get("delivery", "")) if part.strip())
    pcm = providers.gemini_speech(voice["model"], segment["text"], voice["voice_name"], style)
    raw = project.path(f"audio/raw/{segment['id']}-{fingerprint[:12]}.pcm")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(pcm)
    return _finish(project, segment, fingerprint, raw, "gemini",
                   {"input_args": ["-f", "s16le", "-ar", "24000", "-ac", "1"]})


def generate(project, *, only: str | None = None, wait_seconds: int = 300) -> list[str]:
    project.require("content")
    voice = channel_profile.voice_config(project.channel, project.voice_preset)
    done = []
    for segment in project.segments:
        if only and segment["id"] != only:
            continue
        fingerprint = project.audio_fingerprint(segment)
        record = project.state["audio"].get(segment["id"])
        if record and record.get("input_sha256") == fingerprint and project.path(record["path"]).is_file() \
                and file_hash(project.path(record["path"])) == record["sha256"]:
            continue
        if voice["service"] == "genmax":
            _genmax_one(project, segment, fingerprint, voice, wait_seconds)
        else:
            _gemini_one(project, segment, fingerprint, voice)
        done.append(segment["id"])
    return done


def reconcile(project) -> list[str]:
    """Resolve submits with unknown outcome by matching exact text in Genmax history."""
    notes = []
    history = None
    for segment_id, pending in list(_pending(project).items()):
        if pending.get("status") != "submitting":
            continue
        history = history if history is not None else providers.genmax_history()
        matches = [t for t in history if t.get("text") == pending["text"] and str(t.get("created_at", "")) >= pending["at"][:13]]
        if not matches:
            _pending(project).pop(segment_id)
            notes.append(f"{segment_id}: no matching Genmax task; the submit did not land and may be sent again")
        else:
            latest = max(matches, key=lambda t: str(t.get("created_at", "")))
            pending.update(status="submitted", task_id=str(latest["id"]))
            extra = f" ({len(matches) - 1} other matching task(s) left unused)" if len(matches) > 1 else ""
            notes.append(f"{segment_id}: adopted Genmax task {latest['id']}{extra}")
    project.save()
    return notes


BEATS_VERSION = 3


def beats(project, segment: dict) -> list[float]:
    """One onset per sentence: beat i is where sentence i starts in the real audio.

    Voices pause at commas as well as full stops, so the sentence breaks are the
    longest pauses inside the speech (one fewer than the sentence count). When a
    voice runs sentences together, missing breaks are estimated from the length
    of each sentence's text between the breaks that were measured.
    """
    record = project.state["audio"].get(segment["id"])
    if not record:
        raise FitnessError(f"No narration for {segment['id']}")
    cached = project.state["timing"].get(segment["id"])
    if cached and cached.get("audio_sha256") == record["sha256"] and cached.get("version") == BEATS_VERSION:
        return cached["beats"]
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", project.path(record["path"]), "-af",
                  "silencedetect=noise=-40dB:d=0.07", "-f", "null", "-"], timeout=300)
    log = result.stderr.decode("utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
    speech_end = record["speech_seconds"]
    first = ends[0] if starts and starts[0] <= 0.02 and ends else 0.0
    gaps = sorted(round(e, 3) for s, e in zip(starts, ends) if first + 0.3 < e < speech_end - 0.15)
    parts = sentences(segment["text"])
    weights = [len(p) for p in parts]
    # Expected start of each sentence from its share of the text; snap it to the nearest later pause.
    expected = [first + (speech_end - first) * sum(weights[:i]) / sum(weights) for i in range(len(parts))]
    onsets, measured, previous = [round(first, 3)], 1, first
    for target in expected[1:]:
        options = [g for g in gaps if g > previous + 0.3 and abs(g - target) <= 1.0]
        pick = min(options, key=lambda g: abs(g - target)) if options else None
        if pick is not None:
            measured += 1
        previous = pick if pick is not None else max(target, previous + 0.3)
        onsets.append(round(previous, 3))
    phrases = sorted(set(onsets) | {g for g in gaps if g > first + 0.3})  # every pause onset, commas included
    project.state["timing"][segment["id"]] = {"audio_sha256": record["sha256"], "beats": onsets, "version": BEATS_VERSION,
                                              "measured": measured, "sentences": len(parts), "phrases": phrases}
    project.save()
    return onsets


class Beats(list):
    """Sentence onsets; indices past the last sentence continue through the comma pauses (`phrases`)."""

    def __init__(self, sentence_onsets, phrases):
        super().__init__(sentence_onsets)
        self.phrases = phrases


def timed_beats(project, segment: dict) -> Beats:
    onsets = beats(project, segment)
    return Beats(onsets, project.state["timing"][segment["id"]].get("phrases", onsets))


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]
