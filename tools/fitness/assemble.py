"""Join scene clips with the narration, optional licensed music and loudness.

The preview uses the same timing and mix as the delivery file and only lowers
resolution/bitrate. The final MP4 copies the approved scene video streams.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from . import channel as channel_profile
from .common import FitnessError, file_hash, now, probe, run, write_json


LOUDNESS = {"I": -14, "TP": -1.5, "LRA": 11}
# Gentle ducking: short scene gaps (~0.35 s) let the bed come back instead of staying squashed.
DUCK = {"threshold": 0.06, "ratio": 3, "attack": 15, "release": 180}


def _scene_records(project) -> list[dict]:
    from .scenes import scene_fingerprint
    records = []
    for segment in project.segments:
        record = project.state["scenes"].get(segment["id"])
        if not record or record.get("input_sha256") != scene_fingerprint(project, segment) or not project.path(record["path"]).is_file():
            raise FitnessError(f"Scene {segment['id']} render is missing or stale: run `visuals`")
        records.append(record)
    return records


def _concat_list(paths: list[Path], target: Path) -> Path:
    target.write_text("".join(f"file '{p.as_posix()}'\n" for p in paths), encoding="utf-8")
    return target


def _mix(project, work: Path, seconds: float) -> Path:
    narration = work / "narration.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i",
         _concat_list([project.path(project.state["audio"][s["id"]]["path"]) for s in project.segments], work / "audio.txt"),
         "-c:a", "pcm_s16le", narration])
    music = project.channel.get("music")
    graph = "[0:a]aformat=channel_layouts=stereo,aresample=48000[voice]"
    inputs = ["-i", narration]
    mixed = "[voice]"
    if music:
        bed = channel_profile.path(music["path"])
        if not bed.is_file():
            raise FitnessError(f"Music bed not found: {bed}")
        inputs += ["-stream_loop", "-1", "-i", bed]
        gain = float(music.get("gain_db", -16))
        duck = {**DUCK, **(music.get("duck") or {})}
        graph += (f";[1:a]aformat=channel_layouts=stereo,aresample=48000,volume={gain}dB,afade=t=in:d=1.5,"
                  f"afade=t=out:st={max(0, seconds - 2.5):.3f}:d=2.5[bed];[voice]asplit=2[voice][key];"
                  f"[bed][key]sidechaincompress=threshold={duck['threshold']}:ratio={duck['ratio']}:"
                  f"attack={duck['attack']}:release={duck['release']}[ducked];"
                  "[voice][ducked]amix=inputs=2:duration=first:normalize=0[mix]")
        mixed = "[mix]"
    target = ":".join(f"{k}={v}" for k, v in LOUDNESS.items())
    measure = run(["ffmpeg", "-hide_banner", "-nostats", *inputs, "-filter_complex",
                   f"{graph};{mixed}loudnorm={target}:print_format=json[out]", "-map", "[out]", "-t", f"{seconds:.6f}", "-f", "null", "-"])
    stats = json.loads(re.search(r"\{\s*\"input_i\"[\s\S]*?\}", measure.stderr.decode("utf-8", "replace")).group())
    measured = (f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:"
                f"measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true")
    output = work / "mix.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex",
         f"{graph};{mixed}loudnorm={target}:{measured},aresample=48000[out]", "-map", "[out]",
         "-t", f"{seconds:.6f}", "-c:a", "pcm_s16le", output])
    return output


def narration_review(project) -> Path:
    """One compressed MP3 of all segments, joined exactly as in the video, for listening."""
    output = project.path("review/narration.mp3")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        listing = _concat_list([project.path(project.state["audio"][s["id"]]["path"]) for s in project.segments], Path(tmp) / "audio.txt")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
             "-c:a", "libmp3lame", "-b:a", "128k", output])
    return output


def _assemble(project, output: Path, *, preview: bool) -> dict:
    records = _scene_records(project)
    seconds = sum(r["seconds"] for r in records)
    width, height, _ = project.size
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        videos = _concat_list([project.path(r["path"]) for r in records], work / "video.txt")
        mix = _mix(project, work, seconds)
        if preview:
            scale = "scale=720:-2" if width < height else "scale=-2:720"
            video = ["-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p"]
            sound = ["-c:a", "aac", "-b:a", "128k"]
        else:
            video = ["-c:v", "copy"]
            sound = ["-c:a", "aac", "-b:a", "192k"]
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", videos, "-i", mix,
             "-map", "0:v:0", "-map", "1:a:0", *video, *sound, "-t", f"{seconds:.6f}", "-movflags", "+faststart", output],
            timeout=7200)
    info = probe(output)
    if abs(info["duration"] - seconds) > 0.1:
        raise FitnessError(f"Assembled duration {info['duration']:.2f}s differs from the planned {seconds:.2f}s")
    return {"path": project.rel(output), "sha256": file_hash(output), "seconds": round(info["duration"], 3),
            "bytes": output.stat().st_size, "scenes": {s["id"]: project.state["scenes"][s["id"]]["sha256"] for s in project.segments},
            "created_at": now()}


def preview(project) -> dict:
    project.require("media")
    record = _assemble(project, project.path("render/preview.mp4"), preview=True)
    project.state["outputs"]["preview"] = record
    project.save()
    return record


def final(project) -> dict:
    project.require("render")
    record = _assemble(project, project.path("render/final.mp4"), preview=False)
    width, height, fps = project.size
    record.update(width=width, height=height, fps=fps)
    project.state["outputs"]["final"] = record
    project.save()
    write_json(project.path("render/delivery.json"), {
        "file": record["path"], "sha256": record["sha256"], "seconds": record["seconds"],
        "width": width, "height": height, "fps": fps, "aspect": project.brief["aspect"],
        "approvals": project.state["approvals"], "voice": {k: v for k, v in channel_profile.voice_config(project.channel, project.voice_preset).items() if k in ("service", "voice_id", "voice_name", "model_id", "voice")},
        "audio": {k: v["sha256"] for k, v in project.state["audio"].items()},
        "poses": {k: {"sha256": v["sha256"], "model": v.get("model")} for k, v in project.state["poses"].items()},
        "scenes": record["scenes"], "music": project.channel.get("music"), "created_at": record["created_at"],
    })
    return record
