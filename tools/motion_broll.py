"""Bridge a locked video-use cut to the vendored motion-broll engine.

No speech is transcribed here: the existing word-level video-use cache is
retimed onto the edited output. Original EDL and final MP4 remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_path(name: str) -> Path:
    if not name or name in {".", ".."} or any(c in name for c in "/\\:"):
        raise ValueError("--project must be one folder name below projects/")
    project = (PROJECTS / name).resolve()
    if project.parent != PROJECTS.resolve() or not project.is_dir():
        raise ValueError(f"Project folder not found: {project}")
    return project


def inside(path: Path, directory: Path) -> bool:
    return path == directory or directory in path.parents


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{milliseconds:03}"


def edl_info(project: Path) -> tuple[Path, dict, str, float]:
    path = project / "edit/edl.json"
    raw = path.read_bytes()
    edl = json.loads(raw.decode("utf-8-sig"))
    duration = 0.0
    if not edl.get("ranges"):
        raise ValueError("EDL has no ranges")
    for segment in edl["ranges"]:
        if segment["source"] not in edl["sources"]:
            raise ValueError(f"Unknown source: {segment['source']}")
        start, end = float(segment["start"]), float(segment["end"])
        if not all(map(math.isfinite, (start, end))) or start < 0 or end <= start:
            raise ValueError("Invalid EDL range")
        duration += end - start
    return path, edl, hashlib.sha256(raw).hexdigest(), duration


def timeline(project: Path) -> tuple[Path, int]:
    _, edl, digest, duration = edl_info(project)
    motion = project / "motion"
    work = motion / "work"
    work.mkdir(parents=True, exist_ok=True)
    transcript_cache: dict[str, dict] = {}
    entries: list[tuple[float, float, str]] = []
    offset = 0.0
    for segment in edl["ranges"]:
        source = segment["source"]
        if Path(source).name != source or source in {".", ".."}:
            raise ValueError(f"Invalid source ID for transcript path: {source}")
        start, end = float(segment["start"]), float(segment["end"])
        if source not in transcript_cache:
            transcript_path = project / "edit/transcripts" / f"{source}.json"
            if not transcript_path.is_file():
                raise ValueError(f"Missing cached word transcript: {transcript_path}")
            transcript_cache[source] = read_json(transcript_path)
        for word in transcript_cache[source].get("words", []):
            if word.get("type", "word") != "word":
                continue
            text = str(word.get("text") or "").strip().replace("\n", " ")
            if not text or word.get("start") is None or word.get("end") is None:
                continue
            word_start, word_end = float(word["start"]), float(word["end"])
            if word_end <= start or word_start >= end:
                continue
            cue_start = offset + max(start, word_start) - start
            cue_end = offset + min(end, word_end) - start
            if cue_end - cue_start >= 0.01:
                entries.append((cue_start, cue_end, text))
        offset += end - start
    if not entries:
        raise ValueError("No spoken words found in kept ranges; check transcript cache")
    entries.sort(key=lambda item: item[0])
    srt = work / "edited-words.srt"
    srt.write_text("\n\n".join(
        f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}"
        for index, (start, end, text) in enumerate(entries, 1)
    ) + "\n", encoding="utf-8")
    write_json(work / "timeline.json", {
        "edlSha256": digest,
        "duration": duration,
        "wordCount": len(entries),
        "source": "edit/edl.json + edit/transcripts/*.json",
    })
    return srt, len(entries)


def probe_video(path: Path) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,pix_fmt:format=duration",
        "-of", "json", str(path),
    ], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise ValueError(f"No video stream: {path}")
    return {**streams[0], "duration": float(data["format"]["duration"])}


def attach(project: Path) -> Path:
    edl_path, edl, digest, duration = edl_info(project)
    motion = project / "motion"
    plan_path = motion / "plan.json"
    plan = read_json(plan_path)
    timeline_path = motion / "work/timeline.json"
    if read_json(timeline_path).get("edlSha256") != digest:
        raise ValueError("EDL changed since motion timing was generated; rerun timeline and review the plan")
    base = (motion / str(plan.get("video", ""))).resolve()
    expected_base = (project / "edit/base.mp4").resolve()
    if base != expected_base or not base.is_file():
        raise ValueError("motion/plan.json video must be ../edit/base.mp4 (render the locked cut first)")
    base_info = probe_video(base)
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("motion/plan.json must contain at least one rendered clip")
    overlays = list(edl.get("overlays") or [])
    for clip in clips:
        start, end = float(clip["in"]), float(clip["out"])
        if (not all(map(math.isfinite, (start, end))) or start < 0 or end <= start
                or end > min(duration, base_info["duration"]) + 0.05):
            raise ValueError(f"Invalid clip interval: {clip.get('id', '?')}")
        kind = clip.get("kind")
        if kind not in {"full", "panel"}:
            raise ValueError(f"Unsupported clip kind: {kind}")
        clip_path = (motion / str(clip["file"])).resolve()
        if not inside(clip_path, motion / "out") or not clip_path.is_file():
            raise ValueError(f"Rendered clip must exist under motion/out/: {clip_path}")
        if kind == "panel" and clip_path.suffix.lower() != ".mov":
            raise ValueError("Panel clip must be an alpha .mov")
        info = probe_video(clip_path)
        if info["duration"] + 0.05 < end - start:
            raise ValueError(f"Rendered clip is shorter than its slot: {clip_path.name}")
        if kind == "panel" and "a" not in str(info.get("pix_fmt", "")):
            raise ValueError(f"Panel clip has no alpha channel: {clip_path.name}")
        if (info["width"], info["height"]) != (base_info["width"], base_info["height"]):
            raise ValueError(f"Clip resolution differs from base video: {clip_path.name}")
        overlays.append({
            "file": Path("..") / clip_path.relative_to(project),
            "start_in_output": start,
            "duration": end - start,
        })
    edl["overlays"] = [{**item, "file": str(item["file"]).replace("\\", "/")} for item in overlays]
    output = edl_path.with_name("edl.motion.json")
    write_json(output, edl)
    return output


def setup(project: Path) -> None:
    motion = project / "motion"
    for subdir in ("clips", "dist", "out", "work", "inputs"):
        (motion / subdir).mkdir(parents=True, exist_ok=True)
    for binary in ("node", "npm", "ffmpeg", "ffprobe"):
        if not shutil.which(binary) and not shutil.which(binary + ".cmd"):
            raise ValueError(f"Missing prerequisite: {binary}; run setup/setup.ps1")
    python = ROOT / ".venv/Scripts/python.exe"
    if not python.exists():
        raise ValueError("Kit Python environment missing; run setup/setup.ps1")
    subprocess.run([str(python), "-c", "import numpy"], check=True)
    package_json = motion / "package.json"
    if not package_json.exists():
        package_json.write_text('{"private":true}\n', encoding="utf-8")
    playwright = motion / "node_modules/playwright"
    if not playwright.is_dir():
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        subprocess.run([npm, "install", "--no-audit", "--no-fund", "playwright"], cwd=motion, check=True)
    browser = motion / "node_modules/.bin/playwright.cmd"
    if not browser.exists():
        raise ValueError("Playwright CLI missing after npm install")
    environment = os.environ.copy()
    environment["PLAYWRIGHT_BROWSERS_PATH"] = str(motion / ".cache/ms-playwright")
    subprocess.run([str(browser), "install", "chromium"], cwd=motion, env=environment, check=True)
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=True)
    if "prores_ks" not in encoders.stdout:
        print("Warning: FFmpeg lacks prores_ks; transparent panel .mov renders will fail.")
    print(f"Motion workspace ready: {motion}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "timeline", "attach"))
    parser.add_argument("--project", required=True, help="One folder name under projects/")
    args = parser.parse_args()
    project = project_path(args.project)
    if args.action == "setup":
        setup(project)
    elif args.action == "timeline":
        path, count = timeline(project)
        print(f"{path} ({count} word cues)")
    else:
        print(attach(project))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"motion-broll: {exc}", file=sys.stderr)
        sys.exit(1)
