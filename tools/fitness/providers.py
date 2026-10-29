"""HTTP clients for Genmax (narration) and Gemini (images, optional narration).

Errors never include credentials. A transport failure after a request was
sent is reported as an uncertain outcome; callers must reconcile it instead
of submitting again.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import requests

from .common import FitnessError, redact, secret


GENMAX_BASE = os.environ.get("GENMAX_BASE_URL", "https://api.genmax.io").rstrip("/")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class UncertainOutcome(FitnessError):
    """The request may have reached the provider; do not resubmit blindly."""


def _detail(response: requests.Response, *names: str) -> str:
    try:
        body = response.json()
        message = body.get("detail") or body.get("message") or body.get("error") or body
    except ValueError:
        message = response.text
    return redact(str(message), *names)[:500]


# -- Genmax ---------------------------------------------------------------

def _genmax_key() -> str:
    key = secret("GENMAX_API_KEY")
    if not key:
        raise FitnessError("GENMAX_API_KEY is not configured: run setup/configure.ps1")
    return key


def genmax(method: str, path: str, *, json: dict | None = None, params: dict | None = None, timeout: int = 60) -> dict:
    try:
        response = requests.request(method, GENMAX_BASE + path, json=json, params=params, timeout=timeout,
                                    headers={"xi-api-key": _genmax_key(), "Accept": "application/json"})
    except requests.RequestException as exc:
        if method == "GET":
            raise FitnessError(f"Genmax {path} unreachable: {type(exc).__name__}") from None
        raise UncertainOutcome(f"Genmax {method} {path} outcome is uncertain ({type(exc).__name__})") from None
    if response.status_code >= 400:
        raise FitnessError(f"Genmax {method} {path} failed (HTTP {response.status_code}): {_detail(response, 'GENMAX_API_KEY')}")
    try:
        return response.json()
    except ValueError:
        if method == "GET":
            raise FitnessError(f"Genmax {path} returned non-JSON") from None
        raise UncertainOutcome(f"Genmax {method} {path} returned non-JSON; outcome is uncertain") from None


def genmax_voices(search: str | None = None, page_size: int = 30) -> list[dict]:
    params = {"page_size": page_size}
    if search:
        params["search"] = search
    return genmax("GET", "/v1/default-voices", params=params).get("voices", [])


def genmax_submit(text: str, voice: dict) -> str:
    body = {"text": text, "model_id": voice["model_id"], "provider": voice.get("provider", "elevenlabs"),
            "language_code": voice["language_code"]}
    if voice.get("voice_settings"):
        body["voice_settings"] = voice["voice_settings"]
    result = genmax("POST", f"/v1/text-to-speech/{voice['voice_id']}", json=body, timeout=90)
    task = result.get("id") or result.get("task_id")
    if not task:
        raise UncertainOutcome("Genmax accepted the request without a task id; reconcile with history before retrying")
    return str(task)


def genmax_task(task_id: str) -> dict:
    return genmax("GET", f"/v1/history/{task_id}")


def genmax_history(pages: int = 3) -> list[dict]:
    tasks = []
    for page in range(pages):
        batch = genmax("GET", "/v1/history", params={"page_size": 100, "page": page}).get("tasks", [])
        tasks += batch
        if len(batch) < 100:
            break
    return tasks


def genmax_wait(task_id: str, *, wait_seconds: int = 300, interval: float = 3.0) -> dict:
    deadline = time.monotonic() + wait_seconds
    while True:
        task = genmax_task(task_id)
        status = task.get("status")
        if status == "completed":
            return task
        if status == "failed":
            raise FitnessError(f"Genmax task {task_id} failed: {redact(str(task.get('error')), 'GENMAX_API_KEY')[:300]}")
        if time.monotonic() > deadline:
            raise FitnessError(f"Genmax task {task_id} still {status}; rerun the same command later to keep polling it")
        time.sleep(interval)


def genmax_stt_submit(path, language_code: str = "en") -> str:
    """Upload audio for word-timed transcription; returns the task id (paid)."""
    try:
        with open(path, "rb") as handle:
            response = requests.post(GENMAX_BASE + "/v1/speech-to-text", timeout=300,
                                     headers={"xi-api-key": _genmax_key()},
                                     files={"file": (Path(path).name, handle, "audio/mpeg")},
                                     data={"language_code": language_code, "timestamps_granularity": "word",
                                           "tag_audio_events": "false"})
    except requests.RequestException as exc:
        raise UncertainOutcome(f"Genmax speech-to-text upload outcome is uncertain ({type(exc).__name__})") from None
    if response.status_code >= 400:
        raise FitnessError(f"Genmax speech-to-text failed (HTTP {response.status_code}): {_detail(response, 'GENMAX_API_KEY')}")
    task = (response.json() or {}).get("task_id")
    if not task:
        raise UncertainOutcome("Genmax accepted the upload without a task id")
    return str(task)


def genmax_stt_wait(task_id: str, *, wait_seconds: int = 900, interval: float = 5.0) -> dict:
    deadline = time.monotonic() + wait_seconds
    while True:
        task = genmax("GET", f"/v1/speech-to-text/{task_id}")
        if task.get("status") == "completed":
            return task.get("result") or task
        if task.get("status") == "failed":
            raise FitnessError(f"Genmax transcription {task_id} failed: {redact(str(task.get('detail_error')), 'GENMAX_API_KEY')[:300]}")
        if time.monotonic() > deadline:
            raise FitnessError(f"Genmax transcription {task_id} still {task.get('status')}; rerun to keep polling")
        time.sleep(interval)


def genmax_download(url: str) -> bytes:
    headers = {"xi-api-key": _genmax_key()} if url.startswith(GENMAX_BASE) else {}
    try:
        response = requests.get(url, headers=headers, timeout=120)
    except requests.RequestException as exc:
        raise FitnessError(f"Audio download failed: {type(exc).__name__}") from None
    if response.status_code >= 400 or not response.content:
        raise FitnessError(f"Audio download failed (HTTP {response.status_code})")
    return response.content


# -- Gemini ---------------------------------------------------------------

def gemini_generate(model: str, payload: dict, *, timeout: int = 240) -> dict:
    key = secret("GEMINI_API_KEY")
    if not key:
        raise FitnessError("GEMINI_API_KEY is not configured: run setup/configure.ps1")
    try:
        response = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", json=payload, timeout=timeout,
                                 headers={"x-goog-api-key": key})
    except requests.RequestException as exc:
        raise UncertainOutcome(f"Gemini request outcome is uncertain ({type(exc).__name__}); inspect before retrying") from None
    if response.status_code >= 400:
        raise FitnessError(f"Gemini {model} failed (HTTP {response.status_code}): {_detail(response, 'GEMINI_API_KEY')}; no provider fallback")
    return response.json()


def _inline_parts(result: dict, prefix: str) -> list[bytes]:
    parts = []
    for candidate in result.get("candidates", []):
        for part in (candidate.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and str(inline.get("mimeType") or inline.get("mime_type", "")).startswith(prefix):
                parts.append(base64.b64decode(inline["data"]))
    return parts


def gemini_image(model: str, prompt: str, references: list[bytes], aspect: str, size: str = "1K") -> bytes:
    parts = [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(r).decode()}} for r in references]
    parts.append({"text": prompt})
    result = gemini_generate(model, {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect, "imageSize": size}},
    })
    images = _inline_parts(result, "image/")
    if not images:
        reason = (result.get("candidates") or [{}])[0].get("finishReason", "no image")
        raise FitnessError(f"Gemini returned no image ({reason})")
    return images[-1]


# -- Codex (ChatGPT plan) image generation via the local codex-image skill ----------------

CODEX_SIZES = {"1:1": "1:1", "3:2": "3:2", "2:3": "2:3", "4:3": "3:2", "16:9": "3:2", "5:4": "3:2",
               "3:4": "2:3", "9:16": "2:3", "4:5": "2:3"}


def codex_script() -> Path:
    from .common import ROOT
    candidates = [os.environ.get("FITNESS_CODEX_IMAGE_SCRIPT"), ROOT / ".agents/skills/codex-image/scripts/codex_image.mjs",
                  ROOT / ".claude/skills/codex-image/scripts/codex_image.mjs"]
    script = next((Path(c) for c in candidates if c and Path(c).is_file()), None)
    if not script:
        raise FitnessError("codex-image skill not found (.agents/skills/codex-image)")
    return script


def codex_image(prompt: str, references: list[Path], aspect: str, *, model: str = "gpt-5.6-luna", timeout: int = 360) -> tuple[bytes, dict]:
    """One image from Codex's built-in image tool, cropped from its nearest native size to `aspect`."""
    import io
    import subprocess
    import tempfile

    from PIL import Image

    if aspect not in CODEX_SIZES:
        raise FitnessError(f"Codex cannot make aspect {aspect}")
    with tempfile.TemporaryDirectory() as tmp:
        out, prompt_file = Path(tmp) / "image.png", Path(tmp) / "prompt.txt"
        framing = "" if CODEX_SIZES[aspect] == aspect else f" Leave generous empty black space on all sides; the image will be cropped to {aspect}."
        prompt_file.write_text(prompt + framing, encoding="utf-8")
        arguments = ["node", str(codex_script()), "--out", str(out), "--prompt-file", str(prompt_file),
                     "--aspect", CODEX_SIZES[aspect], "--model", model, "--timeout", str(timeout - 30)]
        for reference in references:
            arguments += ["--ref", str(reference)]
        try:
            result = subprocess.run(arguments, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FitnessError(f"Codex image failed to run ({type(exc).__name__})") from None
        if result.returncode or not out.is_file():
            raise FitnessError("Codex image failed: " + result.stderr.decode("utf-8", "replace").strip()[-400:])
        lines = [l for l in result.stdout.decode("utf-8", "replace").splitlines() if l.strip().startswith("{")]
        meta = json.loads(lines[-1]) if lines else {}
        image = Image.open(out).convert("RGB")
    w, h = image.size
    buffer = io.BytesIO()
    crop_to_aspect(image, aspect).save(buffer, format="PNG")
    return buffer.getvalue(), {"agent_credits": meta.get("agent_credits"), "thread_id": meta.get("thread_id"), "native": [w, h]}


def crop_to_aspect(image, aspect: str):
    """Crop to `aspect`, keeping the drawn subject (non-black content) inside the frame where possible."""
    import numpy as np

    w, h = image.size
    a, b = (int(x) for x in aspect.split(":"))
    if abs(w / h - a / b) <= 0.01:
        return image
    lum = np.asarray(image.convert("L")).astype(np.float32) / 255
    rows, cols = np.where(lum > 0.12)
    if w / h > a / b:  # too wide: choose the horizontal window
        new_w = round(h * a / b)
        lo, hi = (cols.min(), cols.max()) if cols.size else (0, w)
        x = int(min(max((lo + hi) / 2 - new_w / 2, 0), w - new_w)) if hi - lo <= new_w else int(min(max(lo, 0), w - new_w))
        return image.crop((x, 0, x + new_w, h))
    new_h = round(w * b / a)
    lo, hi = (rows.min(), rows.max()) if rows.size else (0, h)
    # Keep the whole subject when it fits; otherwise keep its top (heads, bars, hands) rather than its centre.
    y = int(min(max((lo + hi) / 2 - new_h / 2, 0), h - new_h)) if hi - lo <= new_h else int(min(max(lo, 0), h - new_h))
    return image.crop((0, y, w, y + new_h))


# -- OpenAI-compatible image gateway (local kit patch) -----------------------------------

GATEWAY_SIZES = {"1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536"}


def gateway_image(prompt: str, references: list[Path], aspect: str, *, base: str, model: str = "gpt-image-2.5-sunburst",
                  timeout: int = 600) -> tuple[bytes, dict]:
    """One image from an OpenAI-compatible `/images/edits` endpoint (key: IMAGE_GATEWAY_API_KEY), cropped to `aspect`.

    API That bills images that are still drawing when the client gives up, so a timeout or 524 is uncertain, never retried.
    """
    import io

    from PIL import Image

    if not secret("IMAGE_GATEWAY_API_KEY"):
        raise FitnessError("IMAGE_GATEWAY_API_KEY missing: double-click 2-Nhap-key.cmd")
    if aspect not in CODEX_SIZES:
        raise FitnessError(f"Gateway cannot make aspect {aspect}")
    native = CODEX_SIZES[aspect]
    framing = "" if native == aspect else f" Leave generous empty black space on all sides; the image will be cropped to {aspect}."
    # API That serves images from api.apithat.dev, which skips Cloudflare's ~2 min cut (524) on apithat.dev.
    # Rewritten here, not in channel.image, so existing pose fingerprints and the channel approval stay valid.
    base = base.replace("://apithat.dev/", "://api.apithat.dev/")
    files = [("image[]", (Path(r).name, Path(r).read_bytes(), "image/png")) for r in references]
    data = {"model": model, "prompt": prompt + framing, "size": GATEWAY_SIZES[native]}
    headers = {"Authorization": f"Bearer {secret('IMAGE_GATEWAY_API_KEY')}"}
    try:
        if files:
            response = requests.post(f"{base.rstrip('/')}/images/edits", headers=headers, files=files, data=data, timeout=timeout)
        else:  # illustrations have no references; edits needs at least one image
            response = requests.post(f"{base.rstrip('/')}/images/generations", headers=headers, json=data, timeout=timeout)
    except requests.ConnectTimeout:
        raise FitnessError("Gateway could not be reached (connect timeout); nothing was sent") from None
    except requests.RequestException as exc:
        raise UncertainOutcome(f"Gateway image outcome is uncertain ({type(exc).__name__}); it may have been billed, check usage before retrying") from None
    if response.status_code == 524:
        raise UncertainOutcome("Gateway timed out at the proxy (HTTP 524); the image may have been billed, check usage before retrying")
    if response.status_code >= 400:
        raise FitnessError(f"Gateway {model} failed (HTTP {response.status_code}): {redact(response.text[:300], 'IMAGE_GATEWAY_API_KEY')}")
    try:
        item = response.json()["data"][0]
    except (ValueError, KeyError, IndexError):
        raise FitnessError("Gateway returned no image") from None
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        raw = requests.get(item["url"], timeout=120).content
    else:
        raise FitnessError("Gateway returned no image")
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = image.size
    buffer = io.BytesIO()
    crop_to_aspect(image, aspect).save(buffer, format="PNG")
    return buffer.getvalue(), {"model": model, "native": [w, h], "generation_id": item.get("generation_id")}


def generate_image(image_config: dict, prompt: str, references: list[Path], aspect: str) -> tuple[bytes, dict]:
    """Configured provider first (`codex` by default), then the configured fallback (`gemini`).

    The fallback is the creator's explicit choice; the record says which provider drew the image and why.
    """
    order = [image_config.get("provider", "gemini")] + ([image_config["fallback"]] if image_config.get("fallback") else [])
    errors = []
    for provider in order:
        try:
            if provider == "codex":
                data, meta = codex_image(prompt, references, aspect, model=image_config.get("codex_model", "gpt-5.6-luna"))
            elif provider == "gemini":
                data = gemini_image(image_config.get("model", "gemini-3.1-flash-image"), prompt,
                                    [Path(r).read_bytes() for r in references], aspect, image_config.get("size", "1K"))
                meta = {"model": image_config.get("model", "gemini-3.1-flash-image")}
            elif provider == "gateway":
                data, meta = gateway_image(prompt, references, aspect, base=image_config.get("gateway_base", "https://api.apithat.dev/v1"),
                                           model=image_config.get("gateway_model", "gpt-image-2.5-sunburst"))
            else:
                raise FitnessError(f"Unknown image provider {provider}")
            return data, {"provider": provider, **meta, **({"fallback_reason": errors[-1]} if errors else {})}
        except UncertainOutcome:
            raise  # a request may have been billed; inspect before another provider is tried
        except FitnessError as exc:
            errors.append(f"{provider}: {str(exc)[:300]}")
    raise FitnessError("No image provider succeeded: " + " | ".join(errors))


# -- Gemini Batch API (half price, slower) ------------------------------------------------

def _gemini_rest(method: str, path: str, *, json_body: dict | None = None, params: dict | None = None, timeout: int = 120) -> dict:
    key = secret("GEMINI_API_KEY")
    if not key:
        raise FitnessError("GEMINI_API_KEY is not configured: run setup/configure.ps1")
    try:
        response = requests.request(method, f"{GEMINI_BASE}/{path}", json=json_body, params=params, timeout=timeout,
                                    headers={"x-goog-api-key": key})
    except requests.RequestException as exc:
        if method == "GET":
            raise FitnessError(f"Gemini {path} unreachable: {type(exc).__name__}") from None
        raise UncertainOutcome(f"Gemini {method} {path} outcome is uncertain ({type(exc).__name__}); reconcile before retrying") from None
    if response.status_code >= 400:
        raise FitnessError(f"Gemini {method} {path} failed (HTTP {response.status_code}): {_detail(response, 'GEMINI_API_KEY')}")
    return response.json()


def batch_reference(data: bytes, max_side: int = 768) -> dict:
    """A reference image shrunk for batch requests, which are limited to about 20 MB in total."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
    return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buffer.getvalue()).decode()}}


def gemini_image_request(prompt: str, references: list[bytes], aspect: str, size: str = "1K") -> dict:
    parts = [batch_reference(r) for r in references] + [{"text": prompt}]
    return {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect, "imageSize": size}}}


def gemini_batch_submit(model: str, requests_by_key: dict[str, dict], display_name: str) -> str:
    body = {"batch": {"display_name": display_name, "input_config": {"requests": {"requests": [
        {"request": request, "metadata": {"key": key}} for key, request in requests_by_key.items()]}}}}
    if len(json.dumps(body)) > 19_000_000:
        raise FitnessError("Batch request is larger than the inline limit; generate fewer poses per batch")
    job = _gemini_rest("POST", f"models/{model}:batchGenerateContent", json_body=body, timeout=300)
    if not job.get("name"):
        raise UncertainOutcome("Gemini accepted the batch without a job name; reconcile before retrying")
    return job["name"]


def gemini_batch_get(name: str) -> dict:
    return _gemini_rest("GET", name)


def gemini_batch_list() -> list[dict]:
    data = _gemini_rest("GET", "batches", params={"pageSize": 100})
    return data.get("batches") or data.get("operations") or []


def batch_state(job: dict) -> str:
    """Normalised state: PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED or EXPIRED."""
    raw = (job.get("metadata") or {}).get("state") or job.get("state") or ("SUCCEEDED" if job.get("done") else "PENDING")
    return str(raw).split("_STATE_")[-1]


def batch_outputs(job: dict) -> dict[str, bytes | str]:
    """Image bytes (or an error message) per request key from a finished batch with inline responses."""
    holders = [job.get("response") or {}, (job.get("metadata") or {}).get("output") or {}, job.get("dest") or {}]
    inlined = next((h["inlinedResponses"] for h in holders if h.get("inlinedResponses")), {})
    items = inlined.get("inlinedResponses", inlined) if isinstance(inlined, dict) else inlined
    results = {}
    for index, item in enumerate(items or []):
        key = (item.get("metadata") or {}).get("key", str(index))
        if item.get("error"):
            results[key] = str(item["error"].get("message", item["error"]))[:300]
            continue
        images = _inline_parts(item.get("response") or {}, "image/")
        results[key] = images[-1] if images else "no image in the response"
    return results


def gemini_json(model: str, prompt: str, images: list[bytes]) -> object:
    """Ask a multimodal Gemini model for JSON about the given PNG images."""
    parts = [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(i).decode()}} for i in images]
    parts.append({"text": prompt})
    result = gemini_generate(model, {"contents": [{"role": "user", "parts": parts}],
                                     "generationConfig": {"responseMimeType": "application/json"}})
    text = "".join(p.get("text", "") for c in result.get("candidates", []) for p in (c.get("content") or {}).get("parts", []))
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [-1])
    if start < 0:
        raise FitnessError("Gemini returned no JSON")
    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except ValueError:
        raise FitnessError("Gemini returned invalid JSON") from None
    return value


def gemini_speech(model: str, text: str, voice_name: str, style: str) -> bytes:
    """Return raw 24 kHz mono PCM16 from a prebuilt Gemini voice."""
    prompt = f"{style.strip()}\n\n{text}" if style.strip() else text
    result = gemini_generate(model, {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}}},
    })
    audio = _inline_parts(result, "audio/")
    if not audio:
        raise FitnessError("Gemini TTS returned no audio")
    return audio[-1]
