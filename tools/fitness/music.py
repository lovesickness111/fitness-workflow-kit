"""A new background bed for every video with Google Lyria RealTime (`channel.music.provider: "lyria"`).

The style comes from `brief.music` ({prompt, bpm, brightness, density, negative}). The bed is generated at the
full video length (no looping), faded, levelled to -16 LUFS and checked for dropouts, because the realtime
stream can stall. Every style used is logged in `local/fitness/music_log.json`; a style already used by
another video is refused unless `--allow-repeat`, so the channel does not sound the same twice.

The Lyria session code follows the HyperFrames media-use `lyria-recipe.py` (Apache License 2.0).
"""

from __future__ import annotations

import asyncio
import re
import wave
from pathlib import Path

from .common import CHANNEL_DIR, FitnessError, file_hash, now, read_json, run, secret, write_json


MODEL = "models/lyria-realtime-exp"
SR, CHANNELS, WIDTH = 48000, 2, 2
LOG = CHANNEL_DIR / "music_log.json"
NEGATIVE = "vocals, singing, speech, choir"


def generated(channel: dict) -> bool:
    return (channel.get("music") or {}).get("provider") == "lyria"


def _style_key(spec: dict) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(spec.get("prompt", "")).lower()).strip() + f"|{int(spec.get('bpm', 0))}"


def _log() -> list[dict]:
    return read_json(LOG).get("videos", []) if LOG.is_file() else []


def used_styles() -> list[dict]:
    return _log()


async def _stream(output: Path, seconds: float, spec: dict) -> float:
    from google import genai
    from google.genai import types

    key = secret("GEMINI_API_KEY")
    if not key:
        raise FitnessError("GEMINI_API_KEY is missing: run setup/configure.ps1 (2-Nhap-key.cmd)")
    client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
    target = int(seconds * SR * CHANNELS * WIDTH)
    config = {"bpm": int(spec.get("bpm", 110)), "temperature": 1.0, "density": float(spec.get("density", 0.5)),
              "brightness": float(spec.get("brightness", 0.4))}
    scale = getattr(types.Scale, str(spec.get("scale", "")), None) if spec.get("scale") else None
    if scale:
        config["scale"] = scale
    prompts = [types.WeightedPrompt(text=spec["prompt"], weight=1.0),
               types.WeightedPrompt(text=spec.get("negative") or NEGATIVE, weight=-1.0)]
    buffer = bytearray()
    async with client.aio.live.music.connect(model=MODEL) as session:
        await session.set_weighted_prompts(prompts=prompts)
        await session.set_music_generation_config(config=types.LiveMusicGenerationConfig(**config))
        await session.play()

        async def collect():
            while len(buffer) < target:
                async for message in session.receive():
                    content = message.server_content
                    if content and content.audio_chunks:
                        for chunk in content.audio_chunks:
                            buffer.extend(chunk.data)
                            if len(buffer) >= target:
                                return
                await asyncio.sleep(1e-6)

        try:
            await asyncio.wait_for(collect(), timeout=seconds + 30)
        except TimeoutError:
            pass
    audio = bytes(buffer[:target])
    with wave.open(str(output), "wb") as out:
        out.setnchannels(CHANNELS)
        out.setsampwidth(WIDTH)
        out.setframerate(SR)
        out.writeframes(audio)
    return len(audio) / (SR * CHANNELS * WIDTH)


def dropouts(path: Path, start: float = 2.5, end: float | None = None) -> list[tuple[float, float]]:
    """Silent stretches (stream stalls) inside the bed, ignoring the fade-in and fade-out."""
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "silencedetect=noise=-45dB:d=0.8", "-f", "null", "-"]).stderr.decode("utf-8", "replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[0-9.]+)", log)]
    gaps = list(zip(starts, ends + [float("inf")] * (len(starts) - len(ends))))
    return [(a, b) for a, b in gaps if a >= start and (end is None or a < end)]


def generate(project, *, allow_repeat: bool = False, force: bool = False) -> dict:
    """Write audio/bgm.wav for this project and log its style."""
    if not generated(project.channel):
        raise FitnessError('channel.music.provider is not "lyria"; nothing to generate')
    spec = project.brief.get("music") or {}
    if not str(spec.get("prompt", "")).strip():
        raise FitnessError('Set brief.music.prompt (and bpm, brightness 0-1, density 0-1): a style no earlier video used')
    existing = project.state.get("music")
    output = project.path("audio/bgm.wav")
    if existing and output.is_file() and not force and existing.get("style") == _style_key(spec):
        return existing
    clash = [v for v in _log() if v["style"] == _style_key(spec) and v["project"] != project.name]
    if clash and not allow_repeat:
        raise FitnessError(f"Style already used by {clash[0]['project']}: pick another prompt or tempo (or --allow-repeat)")
    seconds = sum(project.state["audio"][s["id"]]["seconds"] for s in project.segments)
    if not seconds:
        raise FitnessError("Generate the narration first: the bed is made at the full video length")
    raw = project.path("audio/bgm_raw.wav")
    raw.parent.mkdir(parents=True, exist_ok=True)
    length = asyncio.run(_stream(raw, seconds + 3, spec))
    if length < seconds:
        raise FitnessError(f"Lyria returned {length:.1f}s of {seconds:.1f}s; run `music` again")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-af",
         f"atrim=0:{seconds + 0.5:.3f},afade=t=in:d=2,afade=t=out:st={max(0.0, seconds - 3.5):.3f}:d=4,loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", str(SR), "-c:a", "pcm_s16le", output])
    raw.unlink(missing_ok=True)
    gaps = dropouts(output, end=seconds - 4)
    if gaps:
        raise FitnessError(f"The bed has dropouts at {', '.join(f'{a:.1f}s' for a, _ in gaps)}; run `music --force` again")
    record = {"path": project.rel(output), "sha256": file_hash(output), "seconds": round(seconds, 3), "style": _style_key(spec),
              "spec": spec, "model": MODEL, "created_at": now()}
    project.state["music"] = record
    project.save()
    log = [v for v in _log() if v["project"] != project.name]
    log.append({"project": project.name, "style": _style_key(spec), "prompt": spec["prompt"], "bpm": spec.get("bpm"), "created_at": now()})
    write_json(LOG, {"videos": log})
    return record


def bed(project) -> tuple[Path, bool] | None:
    """(path, loop) of the bed to mix: the generated per-video bed, else the channel's licensed track."""
    music = project.channel.get("music")
    if not music:
        return None
    if generated(project.channel):
        record = project.state.get("music")
        path = project.path("audio/bgm.wav")
        if not record or not path.is_file():
            raise FitnessError("channel music is generated per video: run `music --project <name>` before `build`")
        return path, False
    from . import channel as channel_profile
    return channel_profile.path(music["path"]), True
