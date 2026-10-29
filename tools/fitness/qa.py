"""Measured checks of an assembled MP4 plus a frame sheet for visual inspection.

These are metrics only: they never replace the creator listening to the clip.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import imaging
from .common import FitnessError, probe, run, write_json


def _loudness(path: Path) -> dict:
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr.decode("utf-8", "replace")
    summary = log[log.rfind("Summary:"):]
    integrated = re.search(r"I:\s+(-?[0-9.]+) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[0-9.]+) dBFS", summary)
    return {"integrated_lufs": float(integrated.group(1)) if integrated else None, "true_peak_dbfs": float(peak.group(1)) if peak else None}


def _mean_volume(path: Path, start: float, length: float = 0.25) -> float | None:
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", path,
               "-af", "volumedetect", "-f", "null", "-"]).stderr.decode("utf-8", "replace")
    match = re.search(r"mean_volume: (-?[0-9.]+) dB", log)
    return float(match.group(1)) if match else None


def check(project, name: str) -> dict:
    output = project.state["outputs"].get(name)
    if not output:
        raise FitnessError(f"No {name} yet")
    path = project.path(output["path"])
    info = probe(path)
    video = next(s for s in info["streams"] if s.get("codec_type") == "video")
    report = {"file": str(path), "seconds": round(info["duration"], 3), "width": video["width"], "height": video["height"],
              "bytes": path.stat().st_size, **_loudness(path)}
    # Level of the bed in the silent tails between scenes (where only music can play).
    gaps, cursor = [], 0.0
    for segment in project.segments:
        record = project.state["audio"][segment["id"]]
        gap = record["seconds"] - record["speech_seconds"]
        if gap >= 0.2:
            gaps.append(_mean_volume(path, cursor + record["speech_seconds"] + 0.05, min(0.25, gap - 0.1)))
        cursor += record["seconds"]
    measured = [g for g in gaps if g is not None]
    report["gap_mean_volume_db"] = round(sum(measured) / len(measured), 1) if measured else None
    report["notes"] = []
    if report["integrated_lufs"] is not None and abs(report["integrated_lufs"] + 14) > 1.0:
        report["notes"].append("loudness is more than 1 LU away from -14 LUFS")
    if project.channel.get("music") and report["gap_mean_volume_db"] is not None and report["gap_mean_volume_db"] < -45:
        report["notes"].append("music bed is nearly inaudible between scenes; consider a higher channel.music.gain_db")
    # Sound effects sit under the voice: a cue louder than the speech peak sounds like a mistake.
    sfx_track = project.path("audio/sfx.wav")
    if sfx_track.is_file():
        report["sfx_peak_dbfs"] = _loudness(sfx_track)["true_peak_dbfs"]
        if report["sfx_peak_dbfs"] is not None and report["sfx_peak_dbfs"] > -6:
            report["notes"].append(f"sound effects peak at {report['sfx_peak_dbfs']} dBFS; lower channel.sfx.gain_db")
    if name == "preview" and report["bytes"] > 50 * 1024 * 1024:
        report["notes"].append("preview is larger than 50 MB; it may not send through chat")
    # Frame sheet at evenly spaced times.
    with tempfile.TemporaryDirectory() as tmp:
        stills = []
        count = 8 if report["seconds"] > 8 else 4
        for index in range(count):
            t = report["seconds"] * (index + 0.5) / count
            frame = Path(tmp) / f"{index:02d}.png"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", frame])
            stills.append((f"{t:.1f}s", frame, []))
        sheet = imaging.contact_sheet(stills, project.path(f"review/{name}-frames.png"), project.channel["palette"],
                                      thumb_height=480, columns=8)
    report["frames"] = str(sheet)
    write_json(project.path(f"review/{name}-check.json"), report)
    return report
