"""Character reference candidates and per-video pose images (Gemini).

Every pose request carries the reference images of the characters it shows.
Prompts describe a generic gritty sports-manga look; they do not imitate a
named artist or reuse another channel's character.
"""

from __future__ import annotations


from . import channel as channel_profile
from . import imaging, providers
from .common import CHANNEL_DIR, FitnessError, file_hash, now, run_parallel


STYLE = (
    "Full-body 2D manga illustration, black-and-white ink with dense cross-hatching, hyper-detailed muscular "
    "anatomy like a gritty martial-arts sports manga, strong high-contrast grayscale shading. "
    "Pure solid flat black background (#000000) filling the entire frame. Draw every prop the pose names (for "
    "example a wall, step, door frame, bar, towel, rope or table) clearly in the same grayscale ink so the pose makes "
    "physical sense; nothing else: no floor, no scenery, no text, no logo, no watermark, no border. The whole body is visible with a margin "
    "around it, centred, hands and feet not cropped."
)
ILLUSTRATION_STYLE = (
    "2D manga ink illustration, black-and-white with dense cross-hatching and strong high-contrast grayscale shading, "
    "pure solid flat black background (#000000) filling the frame, no text, no letters, no numbers, no logo, no watermark, "
    "no border, one clear subject centred with a margin."
)
COLOUR_NAMES = {"highlight": "vivid red", "accent": "bright green", "warning": "yellow", "signature": "the channel signature colour"}
ASPECTS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"}


def colour_clause(channel: dict, character_ids: list[str]) -> str:
    signatures = channel_profile.signatures(channel, character_ids)
    if not signatures:
        return "The image is entirely grayscale: no colour anywhere."
    items = "; ".join(f"the {s['character']} character's {s['item']} ({s['name']})" for s in signatures)
    return f"The only colour anywhere is: {items}, flat and saturated. Skin, hair, props and everything else stay grayscale."


def candidate_prompt(channel: dict, character_id: str) -> str:
    spec = channel_profile.character(channel, character_id)
    return (f"{STYLE} {colour_clause(channel, [character_id])} Character design reference for a recurring mascot: "
            f"{spec['description']}. Standing upright in a relaxed neutral stance, front view, arms slightly away from the body.")


def pose_characters(project, pose_id: str) -> list[str]:
    pose = project.storyboard["poses"][pose_id]
    if pose.get("kind") == "illustration":  # metaphor, anatomy or prop drawing: characters only if listed
        found = pose.get("characters") or []
    else:
        found = pose.get("characters") or [pose.get("character") or project.channel["default_character"]]
    for character_id in found:
        channel_profile.character(project.channel, character_id)
    return found


def pose_prompt(project, pose_id: str) -> str:
    pose = project.storyboard["poses"][pose_id]
    ids = pose_characters(project, pose_id)
    if pose.get("kind") == "illustration":
        accents = [COLOUR_NAMES.get(c, c) for c in pose.get("colours", [])]
        colour = (f"The only colour anywhere is {' and '.join(accents)}, used just on what the subject highlights; everything else is grayscale."
                  if accents else "The image is entirely grayscale: no colour anywhere.")
        cast = "".join(f" Include the {i} character exactly as in its reference images: {channel_profile.character(project.channel, i)['description']}." for i in ids)
        return f"{ILLUSTRATION_STYLE} {colour}{cast} Subject: {pose['prompt'].strip()}"
    cast, start = [], 1
    for character_id in ids:
        spec = channel_profile.character(project.channel, character_id)
        count = len(spec.get("references", []))
        span = f"reference image {start}" if count == 1 else f"reference images {start}-{start + count - 1}"
        cast.append(f"the {character_id} character ({span}): {spec['description']}")
        start += count
    who = ("Draw exactly this character, identical face, hair, build, proportions and clothing: " if len(ids) == 1
           else "Draw exactly these characters together, each identical to their references: ")
    return f"{STYLE} {colour_clause(project.channel, ids)} {who}{'; '.join(cast)}. Pose: {pose['prompt'].strip()}"


def pose_references(project, pose_id: str) -> list:
    return [p for character_id in pose_characters(project, pose_id) for p in channel_profile.references(project.channel, character_id)]


def pose_signatures(project, pose_id: str) -> list[str]:
    """Colours kept after grayscale processing: character signatures plus an illustration's accents."""
    found = [s["hex"] for s in channel_profile.signatures(project.channel, pose_characters(project, pose_id))]
    palette = project.channel["palette"]
    return found + [palette.get(c, c) for c in project.storyboard["poses"][pose_id].get("colours", [])]


def pose_aspect(project, pose_id: str) -> str:
    aspect = project.storyboard["poses"][pose_id].get("aspect") or ("3:4" if project.brief["aspect"] == "9:16" else "1:1")
    if aspect not in ASPECTS:
        raise FitnessError(f"Pose {pose_id} aspect must be one of {sorted(ASPECTS)}")
    return aspect


def character_candidates(channel: dict, character_id: str, count: int) -> list:
    if not 1 <= count <= 6:
        raise FitnessError("--candidates must be between 1 and 6")
    image = channel.get("image", {})
    signatures = [s["hex"] for s in channel_profile.signatures(channel, [character_id])]
    folder = CHANNEL_DIR / "characters" / character_id / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob("c*.png"))
    start = 1 + max([int(p.stem[1:]) for p in existing if p.stem[1:].isdigit()] or [0])
    made = []
    for number in range(start, start + count):
        data, _ = providers.generate_image(image, candidate_prompt(channel, character_id), [], "3:4")
        raw = folder / "raw" / f"c{number}.png"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(data)
        output = folder / f"c{number}.png"
        made.append((f"c{number}", output, imaging.process(raw, output, signatures)))
    every = sorted(folder.glob("c*.png"), key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0)
    imaging.contact_sheet([(p.stem, p, []) for p in every], folder.parent / "candidates.png", channel["palette"])
    return made


def select_character(channel: dict, character_id: str, candidate: str) -> None:
    source = CHANNEL_DIR / "characters" / character_id / "candidates" / f"{candidate}.png"
    if not source.is_file():
        raise FitnessError(f"Unknown candidate {candidate} for {character_id}")
    channel_profile.add_reference(channel, character_id, source, f"from-{candidate}")


class BatchPending(FitnessError):
    """A Gemini batch is still running; rerun the same command later to collect it."""


def _store(project, pose_id: str, fingerprint: str, data: bytes, made_by: dict) -> dict:
    raw = project.path(f"assets/poses/raw/{pose_id}-{fingerprint[:12]}.png")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(data)
    output = project.path(f"assets/poses/{pose_id}-{fingerprint[:12]}.png")
    info = imaging.process(raw, output, pose_signatures(project, pose_id))
    return {"input_sha256": fingerprint, "path": project.rel(output), "sha256": file_hash(output), "raw": project.rel(raw),
            "model": made_by.get("model") or made_by["provider"], "made_by": made_by,
            "characters": pose_characters(project, pose_id), "created_at": now(), **info}


def _batch(project, pending: list[tuple[str, str]], image: dict, wait_seconds: int) -> list[tuple[str, str]]:
    """First pass through the Gemini Batch API. Returns the poses it could not deliver."""
    import time

    model = image.get("model", "gemini-3.1-flash-image")
    job = project.state.get("image_batch")
    if job and job.get("status") == "submitting":
        raise FitnessError("The last Gemini batch submit has an unknown outcome; run `poses --reconcile-batch` first")
    if not job:
        display_name = f"fitness-{project.name}-{now().replace(':', '')}"
        requests = {pose_id: providers.gemini_image_request(pose_prompt(project, pose_id),
                                                            [p.read_bytes() for p in pose_references(project, pose_id)],
                                                            pose_aspect(project, pose_id), image.get("size", "1K"))
                    for pose_id, _ in pending}
        project.state["image_batch"] = {"status": "submitting", "display_name": display_name, "model": model,
                                        "keys": dict(pending), "at": now()}
        project.save()
        try:
            name = providers.gemini_batch_submit(model, requests, display_name)
        except providers.UncertainOutcome:
            raise
        except FitnessError:
            project.state.pop("image_batch", None)  # rejected outright: nothing was queued
            project.save()
            raise
        job = project.state["image_batch"] = {**project.state["image_batch"], "status": "submitted", "name": name}
        project.save()
    deadline = time.monotonic() + wait_seconds
    while True:
        remote = providers.gemini_batch_get(job["name"])
        state = providers.batch_state(remote)
        if state in ("SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"):
            break
        if time.monotonic() >= deadline:
            raise BatchPending(f"Gemini batch {job['name']} is {state.lower()} ({len(job['keys'])} images); rerun the same command later to collect it")
        time.sleep(min(30, max(1, deadline - time.monotonic())))
    outputs = providers.batch_outputs(remote) if state == "SUCCEEDED" else {}
    current = dict(pending)
    leftovers = []
    for pose_id, fingerprint in pending:
        result = outputs.get(pose_id)
        if isinstance(result, bytes) and job["keys"].get(pose_id) == fingerprint:
            made_by = {"provider": "gemini", "model": model, "mode": "batch", "batch": job["name"]}
            project.state["poses"][pose_id] = _store(project, pose_id, fingerprint, result, made_by)
        else:
            reason = result if isinstance(result, str) else (f"batch {state.lower()}" if state != "SUCCEEDED" else "changed after submit")
            leftovers.append((pose_id, fingerprint))
            project.state.setdefault("batch_fallbacks", {})[pose_id] = reason
    project.state.pop("image_batch", None)
    project.save()
    return [item for item in leftovers if item[0] in current]


def reconcile_batch(project) -> str:
    job = project.state.get("image_batch")
    if not job or job.get("status") != "submitting":
        return "no uncertain Gemini batch"
    match = [b for b in providers.gemini_batch_list()
             if ((b.get("metadata") or {}).get("displayName") or b.get("displayName") or b.get("display_name")) == job["display_name"]]
    if not match:
        project.state.pop("image_batch")
        project.save()
        return f"{job['display_name']}: not found on Gemini; the submit did not land and may be sent again"
    job.update(status="submitted", name=match[0]["name"])
    project.save()
    return f"adopted Gemini batch {match[0]['name']}"


def generate(project, *, only: str | None = None, retake: str | None = None, jobs: int = 2, wait_seconds: int = 900) -> list[str]:
    project.require("content")
    channel_profile.require_approved(project.channel)
    if retake:
        if retake not in project.used_poses():
            raise FitnessError(f"Unknown pose {retake}")
        takes = project.state.setdefault("pose_takes", {})
        takes[retake] = takes.get(retake, 1) + 1
        project.save()
    image = project.channel.get("image", {})
    pending = []
    for pose_id in project.used_poses():
        if only and pose_id != only:
            continue
        fingerprint = project.pose_fingerprint(pose_id)
        record = project.state["poses"].get(pose_id)
        if record and record.get("input_sha256") == fingerprint and project.path(record["path"]).is_file() \
                and file_hash(project.path(record["path"])) == record["sha256"]:
            continue
        pending.append((pose_id, fingerprint))
    made = [pose_id for pose_id, _ in pending]
    # Half-price batch for the first pass when Gemini draws; retakes and single poses stay interactive.
    if image.get("batch") and image.get("provider", "gemini") == "gemini" and not (only or retake) \
            and (len(pending) > 1 or project.state.get("image_batch")):
        pending = _batch(project, pending, image, wait_seconds)

    def work(item):
        pose_id, fingerprint = item
        data, made_by = providers.generate_image(image, pose_prompt(project, pose_id), pose_references(project, pose_id), pose_aspect(project, pose_id))
        reason = project.state.get("batch_fallbacks", {}).get(pose_id)
        return _store(project, pose_id, fingerprint, data, {**made_by, **({"batch_fallback": reason} if reason else {})})

    def done(item, record):
        project.state["poses"][item[0]] = record
        project.state.get("batch_fallbacks", {}).pop(item[0], None)
        project.save()

    run_parallel(pending, work, done, jobs)
    return made


def recrop(project) -> list[str]:
    """Re-crop Codex poses from Codex's kept originals (free): used when an earlier crop cut the subject."""
    import os
    from pathlib import Path

    from PIL import Image

    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "generated_images"
    done = []
    for pose_id, record in project.state["poses"].items():
        made_by = record.get("made_by") or {}
        native = made_by.get("native")
        aspect = pose_aspect(project, pose_id)
        a, b = (int(x) for x in aspect.split(":"))
        if made_by.get("provider") != "codex" or not made_by.get("thread_id") or not native or abs(native[0] / native[1] - a / b) < 0.01:
            continue
        originals = sorted((home / made_by["thread_id"]).glob("*.png"), key=lambda p: p.stat().st_mtime)
        if not originals:
            continue
        with Image.open(originals[-1]) as image:
            providers.crop_to_aspect(image.convert("RGB"), aspect).save(project.path(record["raw"]))
        output = project.path(record["path"])
        info = imaging.process(project.path(record["raw"]), output, pose_signatures(project, pose_id))
        record.update(sha256=file_hash(output), recropped_at=now(), **info)
        project.save()
        done.append(pose_id)
    return done


def missing_layout(project) -> list[str]:
    """Tendon labels used by scenes that still have no position in layout.json."""
    missing = []
    for scene in project.storyboard["scenes"]:
        spots = (project.layout.get("poses", {}).get(scene.get("pose"), {}).get("tendons") or {})
        missing += [f"{scene['pose']}.{label}" for label in scene.get("tendons") or [] if label not in spots]
    return sorted(set(missing))


def sheet(project):
    """Clean pose sheet for the creator, plus a gridded copy for placing glows and focus."""
    items = []
    for pose_id in project.used_poses():
        record = project.state["poses"].get(pose_id)
        if record:
            tendons = list((project.layout.get("poses", {}).get(pose_id, {}).get("tendons") or {}).values())
            items.append((pose_id, project.path(record["path"]), tendons))
    if not items:
        raise FitnessError("No pose images yet: run `poses`")
    imaging.contact_sheet(items, project.path("review/poses-grid.png"), project.channel["palette"], grid=True)
    return imaging.contact_sheet(items, project.path("review/poses.png"), project.channel["palette"])
