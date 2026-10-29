"""Project artifacts, validation, checkpoints and the three approval gates.

Gates: content (research, script, storyboard) -> media (narration and poses)
-> render (scene renders and the draft preview). Each approval is bound to
the digest of exactly what was presented; later edits make it stale.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import channel as channel_profile
from .common import PROJECTS, FitnessError, absolute, digest, file_hash, inside, now, read_json, write_json


ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
GATES = ("content", "media", "render")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SCENE_KEYS = {"segment_id", "pose", "title", "badge", "timer", "bars", "warning", "text", "tendons", "jitter", "zoom", "dim",
              "labels", "marks", "inset", "split", "plan", "table", "meter", "tag",
              "holdbar", "angle", "switch", "dose", "transition", "impact"}
FULL_STAGE = ("split", "plan", "table")


def project_dir(name: str) -> Path:
    if not name or not SAFE_ID.match(name):
        raise FitnessError("--project must be a lowercase folder name (letters, digits, hyphens)")
    return PROJECTS / name


def init(name: str, title: str, aspect: str, voice: str | None = None, tag: str | None = None) -> Path:
    if aspect not in ASPECTS:
        raise FitnessError("--aspect must be 9:16 or 16:9")
    directory = project_dir(name)
    if (directory / "brief.json").exists():
        raise FitnessError(f"Project already exists: {directory}. Resume it with `status`; do not create another one.")
    channel = channel_profile.load()
    if voice and voice not in channel_profile.voice_presets(channel):
        raise FitnessError(f"Unknown voice preset {voice!r}; known: {sorted(channel_profile.voice_presets(channel))}")
    width, height = ASPECTS[aspect]
    write_json(directory / "brief.json", {
        "version": 1, "title": title, "aspect": aspect, "width": width, "height": height, "fps": channel["fps"],
        "audience": "", "viewer_promise": "", "target_seconds": None,
    } | ({"voice": voice} if voice else {}) | ({"tag": tag} if tag else {}))
    write_json(directory / "research/sources.json", {"sources": []})
    write_json(directory / "research/claims.json", {"claims": []})
    write_json(directory / "script.json", {"segments": []})
    write_json(directory / "storyboard.json", {"poses": {}, "scenes": []})
    write_json(directory / "layout.json", {"poses": {}, "scenes": {}})
    write_json(directory / "state.json", empty_state())
    return directory


def empty_state() -> dict:
    return {"version": 1, "approvals": {}, "audio": {}, "timing": {}, "poses": {}, "scenes": {}, "outputs": {}, "qa": {}}


def scene_poses(scene: dict) -> list[str]:
    """Every pose or illustration a scene shows: main pose, inset, split panels, plan cards."""
    found = [scene.get("pose"), (scene.get("inset") or {}).get("pose")]
    found += [(scene.get("split") or {}).get(side, {}).get("pose") for side in ("left", "right")]
    found += [item.get("pose") for item in (scene.get("plan") or {}).get("items", [])]
    return [pose for pose in found if pose]


class Project:
    def __init__(self, name: str):
        self.dir = project_dir(name)
        self.name = name
        if not (self.dir / "brief.json").is_file():
            raise FitnessError(f"Unknown project {name}: run `init` first")
        self.channel = channel_profile.load()
        self.brief = read_json(self.dir / "brief.json")
        self.sources = read_json(self.dir / "research/sources.json")
        self.claims = read_json(self.dir / "research/claims.json")
        self.script = read_json(self.dir / "script.json")
        self.storyboard = read_json(self.dir / "storyboard.json")
        layout = self.dir / "layout.json"
        self.layout = read_json(layout) if layout.is_file() else {"poses": {}, "scenes": {}}
        self.state = read_json(self.dir / "state.json")

    # -- files -----------------------------------------------------------
    def path(self, relative: str) -> Path:
        resolved = absolute(self.dir / relative)
        if not inside(resolved, self.dir):
            raise FitnessError(f"Path must stay inside the project: {relative}")
        return resolved

    def rel(self, path: Path) -> str:
        return Path(os.path.relpath(absolute(path), absolute(self.dir))).as_posix()

    def save(self) -> None:
        write_json(self.dir / "state.json", self.state)

    @property
    def size(self) -> tuple[int, int, int]:
        return self.brief["width"], self.brief["height"], self.brief["fps"]

    @property
    def voice_preset(self) -> str | None:
        """Per-video voice preset (brief.voice); None means the channel default."""
        return self.brief.get("voice")

    @property
    def segments(self) -> list[dict]:
        return self.script["segments"]

    def scene_for(self, segment_id: str) -> dict:
        return next(s for s in self.storyboard["scenes"] if s["segment_id"] == segment_id)

    def tags(self) -> dict[str, dict]:
        """Pinned heading per scene, like headings in a document.

        `brief.tag` opens the video; a scene with `"tag": "<line>"` starts a new main idea and the line carries
        forward until another scene changes it; `"tag": false` hides it on that scene only. `from` is set where
        the heading changes at a cut: the previous scene's line (swap) or "" (slide in after a scene without one).
        """
        current, previous, last, result = self.brief.get("tag"), None, None, {}
        for scene in self.storyboard["scenes"]:
            value = scene.get("tag", True)
            if isinstance(value, str):
                current = value
            text = current if value is not False else None
            change = bool(text) and last is not None and text != last
            result[scene["segment_id"]] = {"text": text, "from": (previous or "") if change else None}
            previous, last = text, text or last
        return result

    def tag_sections(self) -> list[dict]:
        """Where each heading starts: [{segment_id, tag}], in order."""
        sections = []
        for segment_id, tag in self.tags().items():
            if tag["text"] and (not sections or sections[-1]["tag"] != tag["text"]):
                sections.append({"segment_id": segment_id, "tag": tag["text"]})
        return sections

    # -- validation ------------------------------------------------------
    def validate_content(self) -> None:
        brief = self.brief
        if brief.get("aspect") not in ASPECTS or (brief.get("width"), brief.get("height")) != ASPECTS[brief["aspect"]]:
            raise FitnessError("brief.json aspect/size must be 9:16 (1080x1920) or 16:9 (1920x1080)")
        if not str(brief.get("title", "")).strip():
            raise FitnessError("brief.json needs a title")
        if brief.get("tag") is not None and (not isinstance(brief["tag"], str) or not 0 < len(brief["tag"]) <= 60):
            raise FitnessError("brief.tag must be a short line (up to 60 characters), e.g. 'Grip · Full guide · At home · No gym'")
        sources = {s.get("id") for s in self.sources.get("sources", [])}
        for source in self.sources.get("sources", []):
            if not source.get("id") or not source.get("title") or not source.get("locator"):
                raise FitnessError("Every source needs id, title and locator")
        claims = {}
        for claim in self.claims.get("claims", []):
            if not claim.get("id") or not claim.get("text") or not claim.get("source_ids"):
                raise FitnessError("Every claim needs id, text and source_ids")
            if not set(claim["source_ids"]) <= sources:
                raise FitnessError(f"Claim {claim['id']} cites an undeclared source")
            claims[claim["id"]] = claim
        segments = self.segments
        if not segments:
            raise FitnessError("script.json has no segments")
        ids = [s.get("id") for s in segments]
        if len(set(ids)) != len(ids) or not all(isinstance(i, str) and SAFE_ID.match(i) for i in ids):
            raise FitnessError("Segment ids must be unique lowercase slugs")
        for segment in segments:
            if not str(segment.get("text", "")).strip():
                raise FitnessError(f"Segment {segment['id']} has no spoken text")
            if not isinstance(segment.get("delivery", ""), str):
                raise FitnessError(f"Segment {segment['id']} delivery must be a string")
        scenes = self.storyboard.get("scenes", [])
        if [s.get("segment_id") for s in scenes] != ids:
            raise FitnessError("storyboard.scenes must have one scene per script segment, in the same order")
        poses = self.storyboard.get("poses", {})
        for pose_id, pose in poses.items():
            if not SAFE_ID.match(pose_id) or not str(pose.get("prompt", "")).strip():
                raise FitnessError(f"Pose {pose_id} needs a slug id and a prompt")
            for character_id in pose.get("characters") or [pose.get("character") or self.channel["default_character"]]:
                channel_profile.character(self.channel, character_id)
        for scene in scenes:
            unknown = set(scene) - SCENE_KEYS
            if unknown:
                raise FitnessError(f"Scene {scene['segment_id']} has unsupported fields: {sorted(unknown)}")
            for pose in scene_poses(scene):
                if pose not in poses:
                    raise FitnessError(f"Scene {scene['segment_id']} uses unknown pose/illustration {pose}")
            used = [name for name in FULL_STAGE if scene.get(name)]
            if len(used) > 1 or (used and scene.get("pose")):
                raise FitnessError(f"Scene {scene['segment_id']}: {', '.join(used)} fill the stage; use one of them and no pose")
            for side in ("left", "right"):
                panel = (scene.get("split") or {}).get(side, {}) if scene.get("split") else None
                if scene.get("split") and not isinstance(panel, dict):
                    raise FitnessError(f"Scene {scene['segment_id']}: split needs left and right panels")
                if panel and re.search(r"\d", str(panel.get("value", ""))) and panel.get("claim_id") not in claims:
                    raise FitnessError(f"Scene {scene['segment_id']}: split {side} shows a number; add its claim_id")
            if scene.get("meter") and not isinstance(scene["meter"].get("value"), (int, float)):
                raise FitnessError(f"Scene {scene['segment_id']}: meter needs a numeric value")
            tag = scene.get("tag", True)
            if not isinstance(tag, (bool, str)) or (isinstance(tag, str) and not 0 < len(tag.strip()) <= 60):
                raise FitnessError(f"Scene {scene['segment_id']}: tag must be a heading line (up to 60 characters) or false")
            if scene.get("tendons") and not scene.get("pose"):
                raise FitnessError(f"Scene {scene['segment_id']} highlights tendons without a pose")
            for name, required in (("badge", "title"), ("title", "text"), ("warning", "text"), ("bars", "items")):
                if scene.get(name) is not None and (not isinstance(scene[name], dict) or not scene[name].get(required)):
                    raise FitnessError(f"Scene {scene['segment_id']}: {name} must be an object with {required}")
            if scene.get("timer") is not None and not (isinstance(scene["timer"], dict) and isinstance(scene["timer"].get("count"), int) and scene["timer"]["count"] > 0):
                raise FitnessError(f"Scene {scene['segment_id']}: timer needs a positive integer count")
            for bar in (scene.get("bars") or {}).get("items", []):
                if bar.get("claim_id") not in claims:
                    raise FitnessError(f"Scene {scene['segment_id']}: every bar needs a claim_id from research/claims.json")
                if not isinstance(bar.get("value"), (int, float)) or not 0 <= bar["value"] <= 1:
                    raise FitnessError(f"Scene {scene['segment_id']}: bar value must be a 0-1 fraction")
            for item in scene.get("text") or []:
                if not str(item.get("text", "")).strip():
                    raise FitnessError(f"Scene {scene['segment_id']}: empty kinetic text item")

    # -- digests and gates -----------------------------------------------
    def content_digest(self) -> str:
        self.validate_content()
        # The voice choice belongs to the media gate, so switching voices keeps content approval.
        brief = {k: v for k, v in self.brief.items() if k != "voice"}
        return digest({"brief": brief, "sources": self.sources, "claims": self.claims,
                       "script": self.script, "storyboard": self.storyboard})

    def media_inputs(self) -> dict:
        audio = {}
        for segment in self.segments:
            record = self.state["audio"].get(segment["id"])
            if not record or record.get("input_sha256") != self.audio_fingerprint(segment) \
                    or not self.path(record["path"]).is_file() or file_hash(self.path(record["path"])) != record["sha256"]:
                raise FitnessError(f"Narration for {segment['id']} is missing or stale: run `audio`")
            audio[segment["id"]] = record["sha256"]
        poses = {}
        for pose_id in self.used_poses():
            record = self.state["poses"].get(pose_id)
            if not record or record.get("input_sha256") != self.pose_fingerprint(pose_id) \
                    or not self.path(record["path"]).is_file() or file_hash(self.path(record["path"])) != record["sha256"]:
                raise FitnessError(f"Pose {pose_id} is missing or stale: run `poses`")
            poses[pose_id] = record["sha256"]
        return {"audio": audio, "poses": poses}

    def media_digest(self) -> str:
        return digest({"content": self.content_digest(), "channel": channel_profile.channel_digest(self.channel, self.voice_preset),
                       **self.media_inputs()})

    def render_digest(self) -> str:
        from .scenes import scene_fingerprint
        scenes = {}
        for segment in self.segments:
            record = self.state["scenes"].get(segment["id"])
            if not record or record.get("input_sha256") != scene_fingerprint(self, segment) \
                    or not self.path(record["path"]).is_file() or file_hash(self.path(record["path"])) != record["sha256"]:
                raise FitnessError(f"Scene {segment['id']} render is missing or stale: run `visuals`")
            scenes[segment["id"]] = record["sha256"]
        preview = self.state["outputs"].get("preview")
        if not preview or preview.get("scenes") != scenes or not self.path(preview["path"]).is_file() \
                or file_hash(self.path(preview["path"])) != preview["sha256"]:
            raise FitnessError("Draft preview is missing or stale: run `preview`")
        return digest({"media": self.media_digest(), "layout": self.layout, "scenes": scenes, "preview": preview["sha256"]})

    def gate_digest(self, gate: str) -> str:
        if gate not in GATES:
            raise FitnessError(f"Unknown gate {gate}")
        return {"content": self.content_digest, "media": self.media_digest, "render": self.render_digest}[gate]()

    def approved(self, gate: str) -> bool:
        approval = self.state["approvals"].get(gate)
        if not approval:
            return False
        try:
            return approval["sha256"] == self.gate_digest(gate)
        except FitnessError:
            return False

    def require(self, gate: str) -> None:
        for earlier in GATES[:GATES.index(gate) + 1]:
            if not self.approved(earlier):
                raise FitnessError(f"The {earlier} approval is missing or stale for the current files: review and obtain approval first")

    def record_review(self, gate: str, sha: str) -> None:
        """Remember what was presented so `approve` can bind to it without retyping the digest."""
        self.state.setdefault("reviews", {})[gate] = {"sha256": sha, "at": now()}
        self.save()

    def approve(self, gate: str, expected: str | None, decision: str) -> None:
        for earlier in GATES[:GATES.index(gate)]:
            self.require(earlier)
        if expected is None:
            expected = (self.state.get("reviews", {}).get(gate) or {}).get("sha256")
            if not expected:
                raise FitnessError(f"Run `review --gate {gate}` and present it before recording an approval")
        current = self.gate_digest(gate)
        if expected != current:
            raise FitnessError("Files changed since this review; run review again and present the current revision")
        if not decision.strip():
            raise FitnessError("--decision must quote the creator's actual reply")
        self.state["approvals"][gate] = {"sha256": current, "decision": decision.strip(), "at": now()}
        self.save()

    # -- fingerprints ----------------------------------------------------
    def audio_fingerprint(self, segment: dict) -> str:
        voice = channel_profile.voice_config(self.channel, self.voice_preset)
        return digest({"text": segment["text"], "delivery": segment.get("delivery", ""), "voice": voice,
                       "gap": self.channel.get("scene_gap_seconds", 0.35)})

    def used_poses(self) -> list[str]:
        return sorted({pose for scene in self.storyboard["scenes"] for pose in scene_poses(scene)})

    def pose_fingerprint(self, pose_id: str) -> str:
        from .imaging import PROCESS_VERSION
        from .poses import pose_aspect, pose_prompt, pose_references, pose_signatures
        return digest({"prompt": pose_prompt(self, pose_id), "references": [file_hash(p) for p in pose_references(self, pose_id)],
                       "image": self.channel.get("image", {}), "aspect": pose_aspect(self, pose_id),
                       "signatures": pose_signatures(self, pose_id), "process": PROCESS_VERSION,
                       "take": self.state.get("pose_takes", {}).get(pose_id, 1)})
