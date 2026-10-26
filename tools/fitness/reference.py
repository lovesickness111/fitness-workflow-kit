"""Reference mode: learn content structure and illustration style from an existing video.

Inputs: a YouTube URL (metadata, chapters, description and captions via
yt-dlp; no media download) and/or a video file the creator downloaded
themselves (scene keyframes, optional Gemini descriptions of each frame).
Everything stays in the ignored `projects/<p>/reference/` folder.

The reference teaches structure, pacing and visual vocabulary. The new
script is written from scratch, its numbers are verified at the primary
source, and `originality` measures wording overlap with the reference.
"""

from __future__ import annotations

import html
import io
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import imaging, providers
from .common import FitnessError, file_hash, now, probe, read_json, run, write_json


INFO_KEYS = ("id", "title", "channel", "uploader", "upload_date", "duration", "width", "height", "language",
             "description", "chapters", "webpage_url", "view_count", "tags")
HUD = ("timer_ring", "bar_chart", "badge", "warning_box", "kinetic_text", "title_card", "anatomy_highlight",
       "diagram", "photo", "icon", "other")
DESCRIBE_MODEL = "gemini-3.8-flash"
OUR_PACE_WPM = 150  # measured on the pilot narration (Genmax Adam, ~145 wpm)


def folder(project) -> Path:
    path = project.path("reference")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ytdlp(arguments: list[str], cwd: Path) -> bytes:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise FitnessError("yt-dlp is not installed: run `fitness_video.py setup`") from None
    runtime = ["--js-runtimes", "node"] if shutil.which("node") else []
    result = subprocess.run([sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings", *runtime, *arguments],
                            cwd=cwd, capture_output=True, timeout=600)
    if result.returncode:
        raise FitnessError("yt-dlp failed: " + result.stderr.decode("utf-8", "replace")[-800:])
    return result.stdout


# -- transcript ----------------------------------------------------------------

def _seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def _clean(word: str) -> str:
    word = html.unescape(word).strip()
    return "" if re.fullmatch(r"\[.*\]|>>|&gt;&gt;", word) else word


def parse_captions(text: str) -> list[dict]:
    """Timed words from YouTube auto-captions (inline word stamps) or plain VTT/SRT cues."""
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    stamped = any(re.search(r"<\d+:\d+:\d+\.\d+>", b) for b in blocks)
    words = []
    for block in blocks:
        match = re.search(r"(\d+:\d+:\d+[.,]\d+|\d+:\d+[.,]\d+)\s*-->\s*(\d+:\d+:\d+[.,]\d+|\d+:\d+[.,]\d+)", block)
        if not match:
            continue
        start, end = _seconds(match.group(1)), _seconds(match.group(2))
        all_lines = block.splitlines()
        timing = next(i for i, line in enumerate(all_lines) if "-->" in line)
        lines = [line for line in all_lines[timing + 1:] if line.strip()]
        if stamped:
            if not lines or not re.search(r"<\d+:\d+:\d+\.\d+>", lines[-1]):
                continue  # rolling repeat of the previous line
            line = lines[-1]
            head = re.sub(r"<[^>]+>", "", line.split("<", 1)[0])
            words += [{"t": start, "w": w} for w in map(_clean, head.split()) if w]
            for stamp, chunk in re.findall(r"<(\d+:\d+:\d+\.\d+)><c>([^<]*)</c>", line):
                words += [{"t": _seconds(stamp), "w": w} for w in map(_clean, chunk.split()) if w]
        else:
            tokens = [w for w in map(_clean, re.sub(r"<[^>]+>", "", " ".join(lines)).split()) if w]
            step = (end - start) / max(1, len(tokens))
            words += [{"t": round(start + i * step, 3), "w": w} for i, w in enumerate(tokens)]
    return words


def _transcribe_with_genmax(reference: Path, source: Path) -> list[dict]:
    audio_file = reference / "audio.mp3"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-vn", "-ac", "1", "-b:a", "64k", audio_file])
    pending = reference / "stt-task.json"
    task = read_json(pending)["task_id"] if pending.is_file() else None
    if not task:
        task = providers.genmax_stt_submit(audio_file)
        write_json(pending, {"task_id": task, "at": now()})
    result = providers.genmax_stt_wait(task)
    return [{"t": float(w["start"]), "w": w["text"].strip()} for w in result.get("words", [])
            if w.get("type", "word") == "word" and w.get("text", "").strip()]


# -- ingest ------------------------------------------------------------------------

def ingest(project, *, url: str | None = None, video: Path | None = None, subs: Path | None = None,
           transcribe: bool = False) -> dict:
    if not (url or video):
        raise FitnessError("Give --url and/or --video")
    reference = folder(project)
    info = read_json(reference / "info.json") if (reference / "info.json").is_file() else {}
    if url:
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(_ytdlp(["-J", "--skip-download", url], Path(tmp)))
            info.update({k: data.get(k) for k in INFO_KEYS})
            boards = [f for f in data.get("formats") or [] if f.get("format_note") == "storyboard" and f.get("fragments")]
            if boards:  # the hover-preview sprites: frames for the whole video without downloading it
                best = max(boards, key=lambda f: (f.get("width") or 0))
                info["storyboard"] = {"width": best["width"], "height": best["height"], "rows": best["rows"],
                                      "columns": best["columns"], "fragments": [{"url": x["url"], "duration": x["duration"]}
                                                                                for x in best["fragments"]]}
            # Creator-uploaded subtitles first, then the original-language auto captions.
            manual = [l for l in ("en", "en-US", "en-GB") if l in (data.get("subtitles") or {})]
            auto = [l for l in ("en-orig", "en", "en-US") if l in (data.get("automatic_captions") or {})]
            pick = (manual or auto or [None])[0]
            if pick and not subs and not (reference / "captions.vtt").is_file():
                kind = "--write-subs" if manual else "--write-auto-subs"
                try:
                    _ytdlp(["--skip-download", kind, "--sub-langs", pick, "--sub-format", "vtt", "-o", "ref.%(ext)s", url], Path(tmp))
                    found = next(Path(tmp).glob("ref.*.vtt"), None)
                    if found:
                        shutil.copyfile(found, reference / "captions.vtt")
                    info["caption_track"] = f"{'manual' if manual else 'auto'}:{pick}"
                except FitnessError as exc:
                    info["caption_error"] = str(exc)[-300:]
    if video:
        video = Path(video)
        if not video.is_file():
            raise FitnessError(f"Video not found: {video}")
        target = reference / ("source" + video.suffix.lower())
        if not target.is_file() or file_hash(target) != file_hash(video):
            shutil.copyfile(video, target)
        meta = probe(target)
        stream = next(s for s in meta["streams"] if s.get("codec_type") == "video")
        info.setdefault("duration", meta["duration"])
        info.setdefault("width", stream["width"])
        info.setdefault("height", stream["height"])
        info["source_file"] = target.name
    if subs:
        shutil.copyfile(subs, reference / "captions.vtt")
    if (reference / "captions.vtt").is_file():
        words = parse_captions((reference / "captions.vtt").read_text(encoding="utf-8-sig"))
        info["transcript_source"] = "captions"
    elif transcribe and info.get("source_file"):
        words = _transcribe_with_genmax(reference, reference / info["source_file"])
        info["transcript_source"] = "genmax speech-to-text"
    else:
        words = []
        info["transcript_source"] = None
    info.update(ingested_at=now(), url=url or info.get("url"))
    write_json(reference / "info.json", info)
    write_json(reference / "transcript.json", {"words": words})
    report = analyse(project)
    frames_file = reference / "frames.json"
    from_video = frames_file.is_file() and read_json(frames_file).get("source", "").startswith("video")
    if video:
        report["keyframes"] = keyframes(project)
    elif url and info.get("storyboard") and not from_video:
        try:
            report["keyframes"] = storyboard_frames(project)
        except FitnessError as exc:
            report["keyframes_error"] = str(exc)
    return report


def _chapters(info: dict) -> list[dict]:
    chapters = info.get("chapters") or []
    if not chapters:
        return [{"start_time": 0.0, "end_time": float(info.get("duration") or 0), "title": "whole video"}]
    return chapters


def analyse(project) -> dict:
    """Pacing, chapter text and research cited in the description."""
    reference = folder(project)
    info = read_json(reference / "info.json")
    words = read_json(reference / "transcript.json")["words"]
    duration = float(info.get("duration") or (words[-1]["t"] if words else 0))
    chapters = []
    for chapter in _chapters(info):
        start, end = float(chapter["start_time"]), float(chapter.get("end_time") or duration)
        text = " ".join(w["w"] for w in words if start <= w["t"] < end)
        count = len(text.split())
        chapters.append({"title": chapter["title"], "start": start, "end": end, "seconds": round(end - start, 1),
                         "words": count, "wpm": round(count / max(end - start, 1) * 60), "text": text})
    cited = cited_research(info.get("description") or "")
    report = {"title": info.get("title"), "channel": info.get("channel"), "url": info.get("url"), "duration": duration,
              "size": [info.get("width"), info.get("height")], "words": len(words),
              "wpm": round(len(words) / max(duration, 1) * 60) if words else None,
              "transcript_source": info.get("transcript_source"), "caption_error": info.get("caption_error"),
              "chapters": chapters, "cited": cited}
    write_json(reference / "analysis.json", report)
    return report


NAME = r"(?:[A-Z]|[a-z]{1,3}[A-Z])[A-Za-z'\-]+"  # Kubo, deVries, van Wilgen style surnames
CITATION = re.compile(rf"({NAME}(?: et al\.?| (?:&|and) {NAME})?) \(?((?:19|20)\d{{2}})\)?\s*\(([^()]{{3,300}})\)")


def cited_research(description: str) -> list[dict]:
    found = []
    for author, year, note in CITATION.findall(description):
        journal = note.split(":", 1)[0].strip()
        found.append({"citation": f"{author} {year}", "journal": journal, "says": note.split(":", 1)[1].strip() if ":" in note else ""})
    return found


# -- illustrations -----------------------------------------------------------------

def keyframes(project, *, threshold: float = 0.32, max_frames: int = 72) -> dict:
    """One frame shortly after each scene cut (plus long-scene fillers), as labelled sheets."""
    reference = folder(project)
    info = read_json(reference / "info.json")
    source = reference / info["source_file"]
    duration = probe(source)["duration"]
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", source, "-vf", f"select='gt(scene,{threshold})',showinfo",
               "-an", "-f", "null", "-"], timeout=3600).stderr.decode("utf-8", "replace")
    cuts = [0.0] + [float(t) for t in re.findall(r"pts_time:([0-9.]+)", log)]
    cuts += [float(c["start_time"]) for c in info.get("chapters") or []]
    cuts = sorted({round(c, 2) for c in cuts if c < duration - 0.5})
    times = []
    for index, cut in enumerate(cuts):
        end = cuts[index + 1] if index + 1 < len(cuts) else duration
        times.append(min(cut + 0.6, (cut + end) / 2))
        span = end - cut
        if span > 12:  # long scene: sample its motion too
            times += [cut + span * k / math.ceil(span / 8) for k in range(1, math.ceil(span / 8))]
    times = sorted(times)
    if len(times) > max_frames:
        step = len(times) / max_frames
        times = [times[int(i * step)] for i in range(max_frames)]
    frames_dir = _fresh_frames_dir(reference)
    extracted = []
    for t in times:
        target = frames_dir / f"f{t:08.2f}.png"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", source, "-frames:v", "1",
             "-vf", "scale=480:-2", target])
        extracted.append((round(t, 2), target))
    return _finish_frames(project, extracted, f"video file ({len(cuts)} scene cuts)")


def storyboard_frames(project) -> dict:
    """Frames from YouTube's hover-preview sprites (low resolution, about every 5 s); no video download."""
    import requests
    from PIL import Image

    reference = folder(project)
    board = read_json(reference / "info.json").get("storyboard")
    if not board:
        raise FitnessError("This video has no storyboard previews; give --video with a file you downloaded")
    frames_dir = _fresh_frames_dir(reference)
    extracted, start = [], 0.0
    per_sheet = board["rows"] * board["columns"]
    for index, fragment in enumerate(board["fragments"]):
        try:
            response = requests.get(fragment["url"], timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise FitnessError(f"Storyboard download failed ({type(exc).__name__}); retry later or use --video") from None
        sprite = Image.open(io.BytesIO(response.content)).convert("RGB")
        tile_w, tile_h = sprite.width // board["columns"], sprite.height // board["rows"]
        step = fragment["duration"] / per_sheet
        for k in range(per_sheet):
            t = start + k * step
            if t >= start + fragment["duration"] - 0.01:
                break
            x, y = (k % board["columns"]) * tile_w, (k // board["columns"]) * tile_h
            target = frames_dir / f"f{t:08.2f}.png"
            sprite.crop((x, y, x + tile_w, y + tile_h)).save(target)
            extracted.append((round(t + step / 2, 2), target))
        start += fragment["duration"]
    return _finish_frames(project, extracted, f"YouTube storyboard {board['width']}x{board['height']}")


def _fresh_frames_dir(reference: Path) -> Path:
    frames_dir = reference / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)
    for old in reference.glob("keyframes-*.png"):
        old.unlink()
    (reference / "visuals.json").unlink(missing_ok=True)  # descriptions belong to the previous frame set
    return frames_dir


def _signature(path: Path):
    """Small grayscale thumbnail, mean brightness, contrast and an 'illustration' score."""
    import numpy as np
    from PIL import Image, ImageFilter

    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((96, 54))
    a = np.asarray(rgb).astype(np.float32) / 255
    gray = a.mean(-1)
    sat = (a.max(-1) - a.min(-1)) / np.maximum(a.max(-1), 1e-6)
    edges = np.asarray(rgb.convert("L").filter(ImageFilter.FIND_EDGES)).astype(np.float32) / 255
    # Accent colour (HUD, highlights) plus edge density (text, line art) marks an illustrated frame.
    score = float(((sat > 0.45) & (a.max(-1) > 0.35)).mean() * 2 + (edges > 0.25).mean())
    return a[::3, ::3], float(gray.mean()), float(gray.std()), round(score, 4)  # colour thumb: same-luma colours still differ


def _finish_frames(project, extracted: list[tuple[float, Path]], source: str) -> dict:
    """Drop black/transition frames and near-duplicates, label chapters, score and write sheets."""
    import numpy as np

    reference = folder(project)
    chapters = _chapters(read_json(reference / "info.json"))
    frames, previous, dropped = [], None, 0
    for t, path in sorted(extracted):
        thumb, mean, std, score = _signature(path)
        if mean < 0.03 or std < 0.015:  # black frame or flat transition
            path.unlink()
            dropped += 1
            continue
        if previous is not None and float(np.abs(thumb - previous).mean()) < 0.035:
            path.unlink()  # same shot as the frame before
            dropped += 1
            continue
        previous = thumb
        chapter = next((c["title"] for c in reversed(chapters) if float(c["start_time"]) <= t), "")
        frames.append({"t": t, "path": path.name, "chapter": chapter, "score": score})
    sheets = []
    for page in range(math.ceil(len(frames) / 24)):
        chunk = frames[page * 24:(page + 1) * 24]
        items = [(f"{int(f['t'] // 60)}:{f['t'] % 60:04.1f}", reference / "frames" / f["path"], []) for f in chunk]
        sheets.append(str(imaging.contact_sheet(items, reference / f"keyframes-{page + 1}.png", {"highlight": "#FF3B30"},
                                                thumb_height=270, columns=6)))
    write_json(reference / "frames.json", {"source": source, "dropped": dropped, "frames": frames, "sheets": sheets})
    return {"source": source, "frames": len(frames), "dropped": dropped, "sheets": sheets}


def chapter_frames(project, chapter: str, count: int) -> list[dict]:
    """The most illustrated frames of a chapter, spread over its duration (described ones carry their notes)."""
    reference = folder(project)
    if not (reference / "frames.json").is_file():
        return []
    frames = [f for f in read_json(reference / "frames.json")["frames"] if f["chapter"] == chapter]
    described = {round(v["t"], 2): v for v in (read_json(reference / "visuals.json").get("frames", [])
                                               if (reference / "visuals.json").is_file() else [])}
    if not frames or count <= 0:
        return []
    picks = []
    for window in range(count):  # best frame in each equal slice keeps the selection spread out
        part = frames[len(frames) * window // count: max(len(frames) * (window + 1) // count, len(frames) * window // count + 1)]
        best = max(part, key=lambda f: f["score"])
        if best not in picks:
            picks.append(best)
    return [{**f, "description": described.get(round(f["t"], 2))} for f in picks]


DESCRIBE_PROMPT = (
    "These are keyframes from a fitness explainer video, in order. For each frame return one JSON object in an array, "
    "same order, with: t (copy the given time), layout (where the character, text and graphics sit), character (who, pose, "
    "camera view), hud (list using only: " + ", ".join(HUD) + "), on_screen_text (short, as shown), colours (main colours), "
    "motion_hint (what likely moves: zoom, shake, glow, count-up, slide, none), our_template (closest of: pose-stage, "
    "title, bars, timer, warning, kinetic-text, other) and notes (one line on what the visual explains). "
    "Describe only; do not invent text that is not visible. Frame times: "
)


def describe(project, *, model: str = DESCRIBE_MODEL, batch: int = 6) -> dict:
    """Gemini descriptions of each keyframe: the illustration vocabulary to borrow (paid, small)."""
    reference = folder(project)
    frames = read_json(reference / "frames.json")["frames"]
    output = reference / "visuals.json"
    done = {round(v["t"], 2): v for v in (read_json(output)["frames"] if output.is_file() else [])}
    for start in range(0, len(frames), batch):
        chunk = [f for f in frames[start:start + batch] if round(f["t"], 2) not in done]
        if not chunk:
            continue
        images = [(reference / "frames" / f["path"]).read_bytes() for f in chunk]
        answer = providers.gemini_json(model, DESCRIBE_PROMPT + ", ".join(f"{f['t']}s" for f in chunk), images)
        for frame, item in zip(chunk, answer if isinstance(answer, list) else []):
            done[round(frame["t"], 2)] = {**item, "t": frame["t"], "chapter": frame["chapter"]}
        write_json(output, {"model": model, "frames": [done[k] for k in sorted(done)]})
    described = [done[k] for k in sorted(done)]
    counts = {}
    for item in described:
        for hud in item.get("hud") or []:
            counts[hud] = counts.get(hud, 0) + 1
    summary = {"frames": len(described), "hud_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])), "model": model}
    write_json(output, {"model": model, "summary": summary, "frames": described})
    return summary


# -- planning and originality ---------------------------------------------------------

def skeleton(project, target_seconds: float, frames_per_chapter: int = 4) -> dict:
    """Scale the chapter structure to a target length and attach each chapter's best illustration frames."""
    reference = folder(project)
    report = read_json(reference / "analysis.json")
    total = sum(c["seconds"] for c in report["chapters"]) or 1
    rows = []
    for chapter in report["chapters"]:
        seconds = target_seconds * chapter["seconds"] / total
        words = round(seconds * OUR_PACE_WPM / 60)
        frames = chapter_frames(project, chapter["title"], frames_per_chapter)
        rows.append({"chapter": chapter["title"], "reference_seconds": chapter["seconds"], "target_seconds": round(seconds, 1),
                     "target_words": words, "segments": max(1, round(words / 22)) if words >= 8 else 0,
                     "frames": [{"t": f["t"], "path": f"frames/{f['path']}", "description": f["description"]} for f in frames]})
    sheet = _skeleton_sheet(reference, rows, target_seconds) if any(r["frames"] for r in rows) else None
    result = {"target_seconds": target_seconds, "rows": rows, "sheet": str(sheet) if sheet else None}
    write_json(reference / f"skeleton-{int(target_seconds)}s.json", result)
    return result


def _skeleton_sheet(reference: Path, rows: list[dict], target_seconds: float) -> Path:
    """One row per reference chapter: the plan on the left, its illustration frames on the right."""
    from PIL import Image, ImageDraw

    thumb_h, label_w, pad = 180, 520, 12
    thumbs = [[Image.open(reference / f["path"]).convert("RGB") for f in row["frames"]] for row in rows]
    thumbs = [[t.resize((round(t.width * thumb_h / t.height), thumb_h)) for t in row] for row in thumbs]
    width = label_w + max((sum(t.width + pad for t in row) for row in thumbs), default=0) + pad
    sheet = Image.new("RGB", (width, len(rows) * (thumb_h + pad) + pad), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    big, small = imaging._font(24), imaging._font(18)
    for index, (row, images) in enumerate(zip(rows, thumbs)):
        y = pad + index * (thumb_h + pad)
        draw.text((pad, y + 8), row["chapter"][:38], fill=(255, 255, 255), font=big)
        plan = (f"ref {row['reference_seconds']:.0f}s -> {row['target_seconds']:.0f}s of {target_seconds:.0f}s"
                f"\n~{row['target_words']} words, {row['segments']} segment(s)")
        draw.multiline_text((pad, y + 48), plan, fill=(160, 220, 160), font=small, spacing=6)
        for k, frame in enumerate(row["frames"]):
            note = (frame.get("description") or {}).get("our_template")
            if note:
                draw.text((pad, y + 96 + k * 20), f"{int(frame['t'] // 60)}:{frame['t'] % 60:04.1f} -> {note}", fill=(200, 200, 200), font=small)
        x = label_w
        for image in images:
            sheet.paste(image, (x, y))
            x += image.width + pad
    target = reference / f"skeleton-{int(target_seconds)}s.png"
    sheet.save(target)
    return target


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9%']+", html.unescape(text).lower())


def originality(project, n: int = 6) -> dict:
    """Wording overlap between our script and the reference transcript (shared n-word runs)."""
    words = [w["w"] for w in read_json(folder(project) / "transcript.json")["words"]]
    reference = _tokens(" ".join(words))
    shingles = {tuple(reference[i:i + n]) for i in range(len(reference) - n + 1)}
    segments, covered_total, total = [], 0, 0
    for segment in project.segments:
        tokens = _tokens(segment["text"])
        covered = [False] * len(tokens)
        for i in range(len(tokens) - n + 1):
            if tuple(tokens[i:i + n]) in shingles:
                for k in range(i, i + n):
                    covered[k] = True
        runs, current = [], []
        for token, hit in zip(tokens, covered):
            if hit:
                current.append(token)
            elif current:
                runs.append(" ".join(current))
                current = []
        if current:
            runs.append(" ".join(current))
        covered_total += sum(covered)
        total += len(tokens)
        segments.append({"id": segment["id"], "shared": runs, "longest": max((len(r.split()) for r in runs), default=0)})
    coverage = covered_total / max(total, 1)
    longest = max((s["longest"] for s in segments), default=0)
    result = {"n": n, "coverage": round(coverage, 3), "longest_shared_words": longest, "segments": segments,
              "ok": coverage < 0.1 and longest < 8, "at": now()}
    project.state["originality"] = result
    project.save()
    return result
