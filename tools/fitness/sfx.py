"""Sound effects: one short cue per on-screen event, mixed into `audio/sfx.wav` under the narration.

The cue sounds come from the creator's own pack (for example the free Mister Horse pack). `channel sfx-pack`
trims, fades and levels them once into `local/fitness/sfx/<cue>.wav`; `build` then places them on the
timeline from the same scene configs that drive the visuals, so a moved beat moves its sound too.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from .common import CHANNEL_DIR, FitnessError, now, write_json


SR = 48000
CUES = ("whoosh-short", "whoosh", "pop", "click", "click-soft", "chime", "error", "ping", "notification",
        "impact-bass-1", "impact-bass-2")
# Default picks inside the free Mister Horse SFX pack (folder of .wav files); `--map cue=relative/file.wav` overrides.
MISTER_HORSE = {
    "pop": ("Pop/Hollow Pop 02", 0.4), "click-soft": ("Click/Pen Click 01", 0.3), "click": ("Click/Mouse Click 04", 0.3),
    "whoosh-short": ("Swoosh/Swoosh 02 - 02", 0.5), "whoosh": ("Swoosh/Swoosh 03 - 04", 0.6),
    "impact-bass-1": ("Boom/Soft/Soft Cinematic Boom 06", 2.5), "impact-bass-2": ("Boom/Medium/Medium Cinematic Boom 04", 3.0),
    "chime": ("Rewards/Bells 1 Upward 01", 0.9), "error": ("Doink/Deep Doink 03", 0.5),
    "notification": ("Beep/Arpeggiated UI Beep 01", 0.6), "ping": ("Beep/Single UI Beep 06", 0.5),
}
BODY_RMS = 0.12  # every cue is levelled to the same body loudness; per-event volumes set the balance
DEDUPE = 0.12    # one cue per 0.12 s window, the higher priority wins


def _decode(path: Path, channels: int = 1) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", str(channels), "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    data = np.frombuffer(raw, np.float32).copy()
    return data.reshape(-1, channels) if channels > 1 else data


def _write_wav(path: Path, stereo: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes(pcm.tobytes())


def _body_rms(a: np.ndarray) -> float:
    loud = np.where(np.abs(a) > np.abs(a).max() * 10 ** (-30 / 20))[0]
    seg = a[loud[0]: loud[-1] + 1] if loud.size else a
    return float(np.sqrt(np.mean(seg ** 2))) or 1e-9


def pack_dir(channel: dict) -> Path | None:
    config = channel.get("sfx")
    if not config:
        return None
    folder = CHANNEL_DIR / config.get("pack", "sfx")
    return folder


def build_pack(channel: dict, source: Path, mapping: dict[str, str] | None = None) -> list[str]:
    """Trim leading silence, cap the length, fade the tail and level each cue; write local/fitness/sfx/<cue>.wav."""
    if not source.is_dir():
        raise FitnessError(f"SFX pack folder not found: {source}")
    target = CHANNEL_DIR / ((channel.get("sfx") or {}).get("pack") or "sfx")
    picks = {cue: (f"{name}.wav", length) for cue, (name, length) in MISTER_HORSE.items()}
    for cue, rel in (mapping or {}).items():
        if cue not in CUES:
            raise FitnessError(f"Unknown cue {cue}; cues are {', '.join(CUES)}")
        picks[cue] = (rel, picks.get(cue, ("", 1.0))[1])
    missing = [f"{cue} ({rel})" for cue, (rel, _) in picks.items() if not (source / rel).is_file()]
    if missing:
        raise FitnessError("Not in the pack: " + "; ".join(missing) + ". Map them with --map cue=relative/file.wav")
    built = []
    for cue, (rel, length) in picks.items():
        a = _decode(source / rel)
        a = a[int(np.argmax(np.abs(a) > np.abs(a).max() * 0.02)):][: int(length * SR)]
        fade = min(len(a) // 3, int(0.25 * SR))
        if fade:
            a[-fade:] *= np.linspace(1, 0, fade) ** 2
        a *= BODY_RMS / _body_rms(a)
        if np.abs(a).max() > 0.89:
            a *= 0.89 / np.abs(a).max()
        _write_wav(target / f"{cue}.wav", np.stack([a, a], axis=1))
        built.append(cue)
    write_json(target / "pack.json", {"source": source.name, "picks": {c: picks[c][0] for c in built}, "created_at": now()})
    return built


def events(project) -> list[dict]:
    """Cue list over the whole video, from the same configs the scenes are rendered from."""
    from .scenes import scene_config
    cues: list[dict] = []
    offset = 0.0

    def add(t, cue, vol, pri=1):
        cues.append({"t": round(offset + t, 4), "cue": cue, "vol": vol, "pri": pri})

    for index, segment in enumerate(project.segments):
        c = scene_config(project, segment)
        entry = (c.get("transition") or {}).get("in")
        if index and entry == "blur":
            add(0.0, "whoosh-short", .22, 1)
        elif index and entry == "swipe":
            add(0.0, "whoosh", .26, 5)  # a big move: wins over the first cue of the scene
        if entry == "impact":
            add(0.0, "impact-bass-2", .32, 6)
        if c.get("tagFrom") is not None:
            add(.05, "whoosh-short", .16, 1)
        if c.get("title"):
            add(c["title"]["at"], "pop", .28, 3)
        if c.get("badge"):
            add(c["badge"]["at"], "impact-bass-1", .2, 4)
        for item in c.get("text") or []:
            add(item["at"], "pop" if item.get("accent") else "click-soft", .2 if item.get("accent") else .14, 2)
        if c.get("timer"):
            add(c["timer"]["at"], "click", .24, 4)
            if c["timer"]["at"] + c["timer"]["over"] < c["T"]:
                add(c["timer"]["at"] + c["timer"]["over"], "chime", .24, 4)
        if c.get("bars"):
            add(c["bars"]["at"], "whoosh-short", .18, 2)
        if c.get("warning"):
            add(c["warning"]["at"], "notification", .2, 3)
        if c.get("meter"):
            add(c["meter"]["at"], "click", .2, 3)
        if c.get("inset"):
            add(c["inset"]["at"], "whoosh-short", .18, 2)
        for name in ("split", "plan", "table"):
            if c.get(name):
                add(c[name]["at"], "whoosh-short", .2, 2)
        for i, _ in enumerate((c.get("table") or {}).get("rows") or []):
            add(c["table"]["at"] + i * c["table"].get("stagger", .35), "pop", .18, 2)
        pose = c.get("pose") or {}
        for mark in (pose.get("marks") or []) + (c.get("stageMarks") or []):
            kind = mark.get("type", "x")
            add(mark["at"], {"x": "error", "check": "chime"}.get(kind, "click-soft"), .24 if kind == "x" else .2, 5)
        for label in (pose.get("labels") or []) + (c.get("stageLabels") or []):
            add(label["at"], "pop", .2, 3)
        if c.get("holdbar"):
            h = c["holdbar"]
            add(h["run_at"], "click", .24, 4)
            if h.get("stop_at") is not None:
                add(h["stop_at"], "error", .26, 5)
            elif h["run_at"] + h["goal"] / h["speed"] < c["T"]:
                add(h["run_at"] + h["goal"] / h["speed"], "chime", .24, 4)
        for step in (c.get("angle") or {}).get("steps") or []:
            add(step["at"], "impact-bass-1" if step["deg"] > -8 else "whoosh-short", .2, 4)
        for step in (c.get("switch") or {}).get("steps") or []:
            add(step["at"], "click", .24, 4)
        if c.get("dose"):
            add(c["dose"]["at"], "pop", .24, 3)
        offset += c["T"]
    cues.sort(key=lambda e: e["t"])
    kept: list[dict] = []
    for cue in cues:
        if kept and cue["t"] - kept[-1]["t"] < DEDUPE:
            if cue["pri"] > kept[-1]["pri"]:
                kept[-1] = cue
            continue
        kept.append(cue)
    return kept


def build_track(project) -> Path | None:
    """Write audio/sfx.wav when the channel has an SFX pack; returns None (and leaves any hand-made file) otherwise."""
    folder = pack_dir(project.channel)
    if folder is None:
        return None
    gain = 10 ** (float(project.channel["sfx"].get("gain_db", 0)) / 20)
    timeline = events(project)
    seconds = sum(project.state["audio"][s["id"]]["seconds"] for s in project.segments)
    track = np.zeros((int(seconds * SR) + 1, 2), np.float32)
    cache: dict[str, np.ndarray] = {}
    for event in timeline:
        if event["cue"] not in cache:
            path = folder / f"{event['cue']}.wav"
            if not path.is_file():
                raise FitnessError(f"SFX cue {event['cue']} missing in {folder}: run `channel sfx-pack --source <pack folder>`")
            cache[event["cue"]] = _decode(path, 2)
        sound = cache[event["cue"]] * event["vol"] * gain
        start = int(event["t"] * SR)
        end = min(len(track), start + len(sound))
        if start < end:
            track[start:end] += sound[: end - start]
    output = project.path("audio/sfx.wav")
    _write_wav(output, track)
    write_json(project.path("audio/sfx.json"), {"events": timeline, "created_at": now()})
    return output
