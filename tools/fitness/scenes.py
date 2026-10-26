"""Build one self-contained HTML page per scene and capture it frame by frame.

Timing comes from the measured narration: components with `beat: n` start at
the n-th speech onset; `layout.json` may set an exact `at` (seconds) instead.
Positions of tendon glows and the camera focus also live in `layout.json`, so
tuning them does not reopen content approval.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from PIL import Image

from . import audio, imaging
from .common import RUNTIME, TEMPLATES, FitnessError, digest, file_hash, now, run, run_parallel, which


CAPTURE = Path(__file__).resolve().parent / "capture.mjs"
DEFAULT_AT = {"badge": 0.15, "title": 0.1, "timer": None, "bars": None, "warning": None}


def _at(component: dict | None, override: dict | None, beats: list[float], default: float, name: str, scene_id: str) -> float:
    override = override or {}
    if override.get("at") is not None:
        return float(override["at"])
    if component and component.get("at") is not None:
        return float(component["at"])
    if component and component.get("beat") is not None:
        index = int(component["beat"])
        if 0 <= index < len(beats):
            return beats[index]
        phrases = getattr(beats, "phrases", [])
        if 0 <= index < len(phrases):  # past the last sentence: the next comma pause
            return phrases[index]
        raise FitnessError(f"{scene_id}.{name}: beat {index} does not exist (sentences {list(beats)}, pauses {phrases}); set layout.json scenes.{scene_id}.{name}.at")
    return default


def scene_config(project, segment: dict) -> dict:
    scene = project.scene_for(segment["id"])
    sid = segment["id"]
    width, height, fps = project.size
    record = project.state["audio"].get(sid)
    if not record:
        raise FitnessError(f"No narration for {sid}: run `audio`")
    seconds = record["seconds"]
    beats = audio.timed_beats(project, segment)
    overrides = project.layout.get("scenes", {}).get(sid, {})
    config = {"W": width, "H": height, "T": seconds, "fps": fps, "aspect": project.brief["aspect"], "palette": project.channel["palette"]}

    if scene.get("pose"):
        pose_id = scene["pose"]
        pose_record = project.state["poses"].get(pose_id)
        if not pose_record:
            raise FitnessError(f"Pose {pose_id} has no image: run `poses`")
        pose_layout = project.layout.get("poses", {}).get(pose_id, {})
        tendons = []
        for label in scene.get("tendons") or []:
            spot = (pose_layout.get("tendons") or {}).get(label)
            if not spot:
                raise FitnessError(f"Set layout.json poses.{pose_id}.tendons.{label} (x, y, rx[, ry, rotate] as 0-1 fractions of the image) after inspecting the pose")
            tendons.append({"x": spot["x"], "y": spot["y"], "rx": spot.get("rx", spot.get("r", 0.04)),
                            "ry": spot.get("ry"), "rotate": spot.get("rotate", 0)})
        image_path = project.path(pose_record["path"])
        with Image.open(image_path) as image:
            w, h = image.size
        pose_override = overrides.get("pose", {})
        config["pose"] = {
            "src": "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode(),
            "w": w, "h": h,
            "focus": pose_override.get("focus") or pose_layout.get("focus") or [0.5, 0.55],
            "zoom": pose_override.get("zoom") or scene.get("zoom") or [1.0, 1.07],
            "jitter": float(scene.get("jitter", 0)),
            "jitterAt": float(pose_override.get("jitter_at", 0.3)),
            "tendons": tendons,
            "tendonAt": _at(None, overrides.get("tendons"), beats, beats[1] if len(beats) > 1 else 0.6, "tendons", sid),
            "dim": float(scene.get("dim", 0)),
        }

    for name in ("badge", "title", "timer", "bars", "warning"):
        component = scene.get(name)
        if not component:
            continue
        default = DEFAULT_AT.get(name)
        at = _at(component, overrides.get(name), beats, beats[min(1, len(beats) - 1)] if default is None else default, name, sid)
        item = {**{k: v for k, v in component.items() if k not in ("beat", "at", "until_beat")}, "at": at}
        until = (overrides.get(name) or {}).get("until", component.get("until"))
        if until is None and component.get("until_beat") is not None:
            until = _at({"beat": component["until_beat"]}, None, beats, 0, f"{name}.until_beat", sid) - 0.05
        item["until"] = until
        if name == "timer":
            item["count"] = int(component.get("count", 30))
            item["over"] = float(component.get("over") or max(1.0, min(item["count"], seconds - at - 0.3)))
        if name == "bars":
            claims = {c["id"]: c for c in project.claims["claims"]}
            titles = {s["id"]: s.get("short") or s["title"] for s in project.sources["sources"]}
            cited = []
            for bar in component["items"] if "items" in component else []:
                for source_id in claims[bar["claim_id"]]["source_ids"]:
                    if titles[source_id] not in cited:
                        cited.append(titles[source_id])
            item["sources"] = "Source: " + "; ".join(cited) if cited else ""
        config[name] = item

    _extended_components(project, scene, config, overrides, beats, seconds, sid)
    if project.brief.get("tag") and scene.get("tag", True) is not False:
        config["tag"] = project.brief["tag"]

    texts = scene.get("text") or []
    text_overrides = overrides.get("text") or {}
    timed = []
    for index, entry in enumerate(texts):
        override = text_overrides.get(str(index)) if isinstance(text_overrides, dict) else None
        phrases = getattr(beats, "phrases", [])
        fallback = beats[index] if index < len(beats) else (phrases[index] if index < len(phrases) else (timed[-1]["at"] + 1.2 if timed else 0.2))
        at = _at(entry, override, beats, fallback, f"text.{index}", sid)
        until = (override or {}).get("until", entry.get("until"))
        if until is None and entry.get("until_beat") is not None:
            until = _at({"beat": entry["until_beat"]}, None, beats, 0, f"text.{index}.until_beat", sid) - 0.05
        timed.append({"text": entry["text"], "accent": entry.get("accent", []), "at": at, "until": until})
    for index, item in enumerate(timed):
        if item["until"] is None:
            item["until"] = timed[index + 1]["at"] - 0.05 if index + 1 < len(timed) else seconds - 0.12
    config["text"] = timed
    if config.get("bars") and config.get("timer") and project.brief["aspect"] == "9:16":
        if config["bars"]["until"] is None or config["bars"]["until"] > config["timer"]["at"]:
            raise FitnessError(f"{sid}: in 9:16 the bars panel covers the timer; end the bars (until/until_beat) before the timer starts, or split the scene")
    return config


def _image(project, pose_id: str) -> dict:
    record = project.state["poses"].get(pose_id)
    if not record:
        raise FitnessError(f"Pose {pose_id} has no image: run `poses`")
    path = project.path(record["path"])
    with Image.open(path) as image:
        w, h = image.size
    return {"src": "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode(), "w": w, "h": h}


def _spots(project, pose_id: str, labels: list[str]) -> list[dict]:
    known = project.layout.get("poses", {}).get(pose_id, {}).get("tendons") or {}
    missing = [label for label in labels if label not in known]
    if missing:
        raise FitnessError(f"Set layout.json poses.{pose_id}.tendons.{missing[0]} (x, y, rx as 0-1 fractions) after inspecting the image")
    return [{"x": known[l]["x"], "y": known[l]["y"], "rx": known[l].get("rx", known[l].get("r", 0.04)),
             "ry": known[l].get("ry"), "rotate": known[l].get("rotate", 0)} for l in labels]


def _when(item: dict, override: dict | None, beats: list[float], default: float, name: str, sid: str) -> tuple[float, float | None]:
    at = _at(item, override, beats, default, name, sid)
    until = (override or {}).get("until", item.get("until"))
    if until is None and item.get("until_beat") is not None:
        until = _at({"beat": item["until_beat"]}, None, beats, 0, f"{name}.until_beat", sid) - 0.05
    return at, until


def _placed(entries: list[dict], overrides: list | dict | None, beats, default, name, sid) -> list[dict]:
    """Labels/marks with positions from the storyboard, adjustable per index in layout.json."""
    placed = []
    for index, entry in enumerate(entries or []):
        override = (overrides or {}).get(str(index)) if isinstance(overrides, dict) else None
        at, until = _when(entry, override, beats, default, f"{name}.{index}", sid)
        placed.append({**{k: v for k, v in entry.items() if k not in ("beat", "until_beat")}, **(override or {}), "at": at, "until": until})
    return placed


def _extended_components(project, scene: dict, config: dict, overrides: dict, beats: list[float], seconds: float, sid: str) -> None:
    """Callouts, marks, inset close-ups, split comparisons, plan rows, tier tables and the effort meter."""
    first = beats[min(1, len(beats) - 1)]
    labels = _placed(scene.get("labels"), overrides.get("labels"), beats, first, "labels", sid)
    marks = _placed(scene.get("marks"), overrides.get("marks"), beats, first, "marks", sid)
    if config.get("pose"):
        config["pose"].update(labels=labels, marks=marks)
    else:
        config.update(stageLabels=labels, stageMarks=marks)
    if scene.get("meter"):
        c = scene["meter"]
        at, until = _when(c, overrides.get("meter"), beats, first, "meter", sid)
        config["meter"] = {"label": c.get("label", "EFFORT"), "value": float(c["value"]), "max": int(c.get("max", 10)),
                           "caption": c.get("caption"), "at": at, "until": until}
    if scene.get("inset"):
        c = scene["inset"]
        at, until = _when(c, overrides.get("inset"), beats, first, "inset", sid)
        config["inset"] = {"image": _image(project, c["pose"]), "spots": _spots(project, c["pose"], c.get("spots") or []),
                           "label": c.get("label"), "accent": c.get("accent", []), "at": at, "until": until,
                           "labels": _placed(c.get("labels"), None, beats, at + 0.4, "inset.labels", sid),
                           "marks": _placed(c.get("marks"), None, beats, at + 0.4, "inset.marks", sid)}
    if scene.get("split"):
        c = scene["split"]
        at, _ = _when(c, overrides.get("split"), beats, 0.2, "split", sid)
        panels = []
        for index, side in enumerate(("left", "right")):
            panel = dict(c[side])
            panel_at, _ = _when(panel, (overrides.get("split") or {}).get(side), beats, at + index * 0.6, f"split.{side}", sid)
            if panel.get("pose"):
                panel["image"] = _image(project, panel["pose"])
                panel["spots"] = _spots(project, panel["pose"], panel.get("spots") or [])
            panels.append({**{k: v for k, v in panel.items() if k not in ("beat", "pose", "claim_id")}, "at": panel_at})
        config["split"] = {"title": c.get("title"), "sub": c.get("sub"), "accent": c.get("accent", []), "at": at,
                           "left": panels[0], "right": panels[1]}
    if scene.get("plan"):
        c = scene["plan"]
        at, _ = _when(c, overrides.get("plan"), beats, 0.2, "plan", sid)
        config["plan"] = {"title": c.get("title"), "sub": c.get("sub"), "accent": c.get("accent", []), "at": at,
                          "stagger": c.get("stagger", 0.3),
                          "items": [{"image": _image(project, i["pose"]), "label": i["label"], "color": i.get("color")} for i in c["items"]]}
    if scene.get("table"):
        c = scene["table"]
        at, _ = _when(c, overrides.get("table"), beats, 0.2, "table", sid)
        config["table"] = {"title": c.get("title"), "sub": c.get("sub"), "accent": c.get("accent", []), "at": at,
                           "stagger": c.get("stagger", 0.35), "rows": c["rows"]}


def scene_html(config: dict) -> str:
    font = base64.b64encode((TEMPLATES / "fonts/Montserrat-Variable.ttf").read_bytes()).decode()
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    runtime = (TEMPLATES / "runtime.js").read_text(encoding="utf-8")
    data = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            f"@font-face{{font-family:'Montserrat';src:url(data:font/ttf;base64,{font}) format('truetype');font-weight:100 900}}"
            f"{css}</style></head><body><div id='stage'></div><script>window.SCENE={data};</script>"
            f"<script>{runtime}</script></body></html>")


def scene_fingerprint(project, segment: dict) -> str:
    config = scene_config(project, segment)
    return digest({"html": digest(scene_html(config)), "capture": file_hash(CAPTURE), "crf": 18})


def node_env() -> dict:
    modules = Path(os.environ.get("FITNESS_NODE_MODULES", RUNTIME / "node_modules"))
    if not (modules / "playwright").is_dir():
        raise FitnessError("Playwright runtime missing: run `fitness_video.py setup`")
    return {**os.environ, "NODE_PATH": str(modules)}


def _build(project, segment: dict) -> tuple[Path, dict]:
    config = scene_config(project, segment)
    page = project.path(f"render/build/{segment['id']}.html")
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(scene_html(config), encoding="utf-8")
    return page, config


def render(project, *, only: str | None = None, jobs: int = 2) -> list[str]:
    project.require("media")
    if not which("node"):
        raise FitnessError("Node.js is required")
    env = node_env()
    pending = []
    for segment in project.segments:
        if only and segment["id"] != only:
            continue
        fingerprint = scene_fingerprint(project, segment)
        record = project.state["scenes"].get(segment["id"])
        if record and record.get("input_sha256") == fingerprint and project.path(record["path"]).is_file() \
                and file_hash(project.path(record["path"])) == record["sha256"]:
            continue
        page, config = _build(project, segment)
        output = project.path(f"render/scenes/{segment['id']}-{fingerprint[:12]}.mp4")
        output.parent.mkdir(parents=True, exist_ok=True)
        pending.append((segment["id"], fingerprint, page, config, output))

    def work(item):
        _, _, page, config, output = item
        run(["node", CAPTURE, "video", page, output, config["fps"], "18"], env=env, timeout=7200)
        return file_hash(output)

    def done(item, sha):
        segment_id, fingerprint, _, config, output = item
        project.state["scenes"][segment_id] = {"input_sha256": fingerprint, "path": project.rel(output),
                                               "sha256": sha, "seconds": config["T"], "created_at": now()}
        project.save()

    run_parallel(pending, work, done, jobs)
    return [item[0] for item in pending]


def storyboard(project, jobs: int = 2) -> Path:
    """One sheet with every scene shortly after each measured beat: the whole clip at a glance."""
    shots = []
    for segment in project.segments:
        seconds = project.state["audio"][segment["id"]]["seconds"]
        times = sorted({round(min(b + 0.9, seconds - 0.15), 2) for b in audio.beats(project, segment)})
        shots.append((segment["id"], times))
    frames: dict[str, list[Path]] = {}
    run_parallel(shots, lambda item: stills(project, item[0], item[1]), lambda item, paths: frames.__setitem__(item[0], paths), jobs)
    items = [(f"{sid} @ {p.stem.rsplit('-', 1)[-1]}", p, []) for sid, _ in shots for p in frames[sid]]
    return imaging.contact_sheet(items, project.path("review/storyboard.png"), project.channel["palette"], thumb_height=560, columns=6)


def stills(project, segment_id: str, times: list[float]) -> list[Path]:
    """Inspection frames; allowed before media approval to tune layout.json."""
    segment = next((s for s in project.segments if s["id"] == segment_id), None)
    if not segment:
        raise FitnessError(f"Unknown segment {segment_id}")
    page, config = _build(project, segment)
    prefix = project.path(f"review/stills/{segment_id}")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    times = [round(min(max(0.0, t), config["T"] - 1 / config["fps"]), 2) for t in times]
    run(["node", CAPTURE, "stills", page, prefix, ",".join(f"{t:.3f}" for t in times)], env=node_env(), timeout=600)
    return [Path(f"{prefix}-{t:.2f}s.png") for t in times]
