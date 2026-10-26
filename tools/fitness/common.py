"""Shared paths, JSON/hash helpers, credentials and subprocess wrappers.

Credentials are read from the process environment, then `local/secrets.env`,
then a kit-root `.env`. Values are never printed or written to state.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# Overrides exist for isolated tests; normal use keeps the kit defaults.
PROJECTS = Path(os.environ.get("FITNESS_PROJECTS_DIR", ROOT / "projects"))
LOCAL = Path(os.environ.get("FITNESS_LOCAL_DIR", ROOT / "local"))
CHANNEL_DIR = LOCAL / "fitness"
RUNTIME = Path(os.environ.get("FITNESS_RUNTIME_DIR", ROOT / "local/fitness-runtime"))
TEMPLATES = Path(__file__).resolve().parent / "templates"
SECRET_FILES = (LOCAL / "secrets.env", ROOT / ".env")


class FitnessError(Exception):
    """An expected workflow error with a message meant for the operator."""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".pending")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def absolute(path) -> Path:
    """Lexically normalized absolute path; unlike resolve() it is stable while other threads create folders."""
    return Path(os.path.normpath(os.path.abspath(path)))


def inside(path: Path, directory: Path) -> bool:
    path, directory = (os.path.normcase(str(absolute(p))) for p in (path, directory))
    return path == directory or path.startswith(directory.rstrip(os.sep) + os.sep)


def _secret_file_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in SECRET_FILES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip().strip('"').strip("'")
            if name and value and name not in values:
                values[name] = value
    return values


def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or _secret_file_values().get(name, "")


def secret_present(name: str) -> bool:
    return bool(secret(name))


def redact(text: str, *names: str) -> str:
    for name in names:
        value = secret(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def which(binary: str) -> str | None:
    return shutil.which(binary) or shutil.which(binary + ".cmd") or shutil.which(binary + ".exe")


def run(arguments: list, *, timeout: int = 3600, env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run([str(a) for a in arguments], capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise FitnessError(f"Timed out: {Path(str(arguments[0])).name}") from None
    except OSError as exc:
        raise FitnessError(f"Cannot run {arguments[0]}: {exc}") from None
    if result.returncode:
        tail = result.stderr.decode("utf-8", errors="replace")[-1800:]
        raise FitnessError(f"{Path(str(arguments[0])).name} failed (exit {result.returncode}):\n{tail}")
    return result


def probe(path: Path) -> dict:
    result = run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,width,height,pix_fmt,sample_rate,channels:format=duration",
                  "-of", "json", path], timeout=120)
    data = json.loads(result.stdout)
    data["duration"] = float(data["format"]["duration"])
    return data


def run_parallel(items: list, work, done, jobs: int = 2) -> None:
    """Run `work(item)` on up to `jobs` threads; `done(item, result)` checkpoints on the caller's thread.

    Every successful item is checkpointed even when another fails; the first
    failure is raised afterwards so the command can simply be resumed.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    errors = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(work, item): item for item in items}
        for future in as_completed(futures):
            try:
                done(futures[future], future.result())
            except Exception as exc:  # noqa: BLE001 - reported after the remaining items finish
                errors.append(exc)
    if errors:
        raise errors[0]


def frames(seconds: float, fps: int) -> int:
    return max(1, math.ceil(round(seconds * fps, 6)))
