"""Channel profile in ignored `local/fitness/`: palette, characters, voice, images, music.

The profile belongs to the colleague running the kit. The example in
`config/fitness/` contains no account, voice or character of anyone else.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .common import CHANNEL_DIR, ROOT, FitnessError, absolute, digest, file_hash, inside, now, read_json, secret_present, write_json


EXAMPLE = ROOT / "config/fitness/channel.example.json"
PROFILE = CHANNEL_DIR / "channel.json"
STATE = CHANNEL_DIR / "state.json"
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
PALETTE_KEYS = ("background", "ink", "signature", "highlight", "accent", "warning", "muted")


def init() -> Path:
    if PROFILE.exists():
        return PROFILE
    CHANNEL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EXAMPLE, PROFILE)
    return PROFILE


def load() -> dict:
    if not PROFILE.is_file():
        raise FitnessError("No channel profile yet: run `fitness_video.py channel init`")
    channel = read_json(PROFILE)
    validate(channel)
    return channel


def validate(channel: dict) -> None:
    palette = channel.get("palette") or {}
    for key in PALETTE_KEYS:
        if not HEX.match(str(palette.get(key, ""))):
            raise FitnessError(f"channel.palette.{key} must be a #RRGGBB colour")
    if channel.get("fps") not in (24, 25, 30, 60):
        raise FitnessError("channel.fps must be 24, 25, 30 or 60")
    gap = channel.get("scene_gap_seconds", 0.35)
    if not isinstance(gap, (int, float)) or not 0 <= gap <= 2:
        raise FitnessError("channel.scene_gap_seconds must be between 0 and 2")
    if channel.get("voice", {}).get("provider", "auto") not in ("auto", "genmax", "gemini"):
        raise FitnessError("channel.voice.provider must be auto, genmax or gemini")
    music = channel.get("music")
    if music is not None:
        generated = isinstance(music, dict) and music.get("provider") == "lyria"
        if not generated and (not isinstance(music, dict) or not music.get("path") or not (music.get("provenance") or {}).get("rights")):
            raise FitnessError('channel.music needs path and provenance.rights (licensed music), {"provider": "lyria"} (a new bed per video), or null')
        if not isinstance(music.get("duck", {}), (dict, bool)):
            raise FitnessError("channel.music.duck must be an object of sidechain settings or false")
    sfx = channel.get("sfx")
    if sfx is not None and (not isinstance(sfx, dict) or not isinstance(sfx.get("gain_db", 0), (int, float))):
        raise FitnessError('channel.sfx must be {"pack": "sfx", "gain_db": 0} (build it with `channel sfx-pack`) or null')
    motion = channel.get("motion") or {}
    if motion.get("transition", "blur") not in ("blur", "swipe", "impact", "fade", "cut"):
        raise FitnessError("channel.motion.transition must be blur, swipe, impact, fade or cut")
    characters = channel.get("characters")
    if not isinstance(characters, dict) or not characters:
        raise FitnessError("channel.characters must define at least one character")
    if channel.get("default_character") not in characters:
        raise FitnessError("channel.default_character must name one of channel.characters")
    for character_id, spec in characters.items():
        if not SAFE_ID.match(character_id) or not str(spec.get("description", "")).strip():
            raise FitnessError(f"Character {character_id!r} needs a lowercase id and a description")
        signature = spec.get("signature")
        if signature is not None and (not HEX.match(str(signature.get("hex", ""))) or not signature.get("item") or not signature.get("name")):
            raise FitnessError(f"Character {character_id}: signature needs item, name and #RRGGBB hex, or null")


def add_reference(channel: dict, character_id: str, image: Path, label: str | None = None) -> Path:
    """Import a reference image, cropped to its largest subject so stray marks are left out."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    spec = character(channel, character_id)
    with Image.open(image) as source:
        rgb = source.convert("RGB")
    a = np.asarray(rgb).astype(np.float32) / 255
    subject = ndimage.binary_dilation(a.max(-1) > 0.12, iterations=6)
    labels, count = ndimage.label(subject)
    if not count:
        raise FitnessError(f"No subject found in {image}")
    largest = 1 + int(np.argmax(ndimage.sum(subject, labels, range(1, count + 1))))
    rows, cols = np.where(labels == largest)
    height, width = subject.shape
    margin = int(0.04 * max(height, width))
    box = (max(0, cols.min() - margin), max(0, rows.min() - margin), min(width, cols.max() + margin + 1), min(height, rows.max() + margin + 1))
    existing = spec.setdefault("references", [])
    name = label or f"ref-{len(existing) + 1}"
    if not SAFE_ID.match(name):
        raise FitnessError("--label must be a lowercase slug")
    relative = f"characters/{character_id}/{name}.png"
    target = path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    rgb.crop(box).save(target)
    if relative not in existing:
        existing.append(relative)
    write_json(PROFILE, channel)
    return target


def path(relative: str) -> Path:
    resolved = absolute(CHANNEL_DIR / relative)
    if not inside(resolved, CHANNEL_DIR) or resolved == absolute(CHANNEL_DIR):
        raise FitnessError(f"Channel paths must stay inside local/fitness/: {relative}")
    return resolved


def character(channel: dict, character_id: str | None = None) -> dict:
    character_id = character_id or channel.get("default_character")
    found = (channel.get("characters") or {}).get(character_id)
    if not found:
        raise FitnessError(f"Unknown character {character_id!r}; known: {sorted(channel.get('characters') or {})}")
    return found


def references(channel: dict, character_id: str | None = None) -> list[Path]:
    """Reference images of one character, in the order they are sent to the model."""
    found = [path(p) for p in character(channel, character_id).get("references", [])]
    missing = [p for p in found if not p.is_file()]
    if not found or missing:
        raise FitnessError(f"Character {character_id or channel.get('default_character')} needs reference images "
                           "(`channel add-reference` or `channel character` + `channel select`)")
    return found


def signatures(channel: dict, character_ids: list[str]) -> list[dict]:
    """Signature colour items (e.g. blue shorts) of the given characters; monochrome characters have none."""
    found = []
    for character_id in character_ids:
        signature = character(channel, character_id).get("signature")
        if signature:
            found.append({"character": character_id, **signature})
    return found


def voice_presets(channel: dict) -> dict:
    """Named Genmax voices the creator approved, e.g. {"brian": {"voice_id": ..., "name": ...}}."""
    return channel.get("voice", {}).get("presets") or {}


def voice_provider(channel: dict, preset: str | None = None) -> str:
    """Resolve the configured provider; `auto` prefers Genmax over Gemini.

    Selection happens before any request. A failed request never falls back
    silently to the other provider.
    """
    choice = channel.get("voice", {}).get("provider", "auto")
    if choice == "auto":
        if secret_present("GENMAX_API_KEY"):
            choice = "genmax"
        elif secret_present("GEMINI_API_KEY"):
            choice = "gemini"
        else:
            raise FitnessError("No voice credential: add GENMAX_API_KEY (preferred) or GEMINI_API_KEY with setup/configure.ps1")
    if choice == "genmax":
        chosen = preset or channel["voice"].get("default")
        if chosen and chosen not in voice_presets(channel):
            raise FitnessError(f"Unknown voice preset {chosen!r}; known: {sorted(voice_presets(channel))}")
        if not chosen and not channel["voice"]["genmax"].get("voice_id"):
            raise FitnessError("Choose a Genmax voice first: `channel voices`, `channel sample`, then add it to voice.presets and voice.default")
    return choice


def voice_config(channel: dict, preset: str | None = None) -> dict:
    """The exact voice request settings: the channel default, or a per-video preset."""
    provider = voice_provider(channel, preset)
    config = {**channel["voice"][provider], "service": provider}
    chosen = preset or channel["voice"].get("default")
    if provider == "genmax" and chosen:
        config.update(voice_id=voice_presets(channel)[chosen]["voice_id"], voice_name=voice_presets(channel)[chosen]["name"])
    return config


def identity(channel: dict, preset: str | None = None) -> dict:
    """Everything that changes how generated media looks or sounds (for one voice choice)."""
    characters = {}
    for character_id, spec in (channel.get("characters") or {}).items():
        files = [path(p) for p in spec.get("references", [])]
        characters[character_id] = {**spec, "reference_sha256": [file_hash(p) if p.is_file() else None for p in files]}
    music = channel.get("music")
    if music and music.get("path"):
        bed = path(music["path"])
        music = {**music, "sha256": file_hash(bed) if bed.is_file() else None}
    profile = {
        "palette": channel["palette"],
        "fps": channel["fps"],
        "gap": channel.get("scene_gap_seconds", 0.35),
        "characters": characters,
        "default_character": channel.get("default_character"),
        "voice": voice_config(channel, preset),
        "voice_presets": voice_presets(channel),
        "image": channel.get("image", {}),
        "music": music,
    }
    # Only when set, so channels approved before SFX and motion settings existed keep their approval.
    for key in ("sfx", "motion"):
        if channel.get(key):
            profile[key] = channel[key]
    return profile


def channel_digest(channel: dict, preset: str | None = None) -> str:
    return digest(identity(channel, preset))


def state() -> dict:
    return read_json(STATE) if STATE.is_file() else {"approval": None}


def approval_current(channel: dict) -> bool:
    approval = state().get("approval")
    return bool(approval) and approval.get("sha256") == channel_digest(channel)


def require_approved(channel: dict) -> None:
    references(channel)
    if not approval_current(channel):
        raise FitnessError("The channel voice/character/palette is not approved in its current form: run `channel review`, present it, then `channel approve`")


def record_review(channel: dict) -> str:
    current = channel_digest(channel)
    write_json(STATE, {**state(), "review": {"sha256": current, "at": now()}})
    return current


def approve(channel: dict, expected: str | None, decision: str) -> None:
    references(channel)
    if expected is None:
        expected = (state().get("review") or {}).get("sha256")
        if not expected:
            raise FitnessError("Run `channel review` and present it before recording an approval")
    current = channel_digest(channel)
    if expected != current:
        raise FitnessError("The channel changed since it was reviewed; review it again")
    if not decision.strip():
        raise FitnessError("--decision must quote the creator's actual reply")
    write_json(STATE, {**state(), "approval": {"sha256": current, "decision": decision.strip(), "at": now()}})
