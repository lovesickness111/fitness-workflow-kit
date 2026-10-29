"""Synthesize a full-length SFX track (whooshes, hits, pops, beeps) timed to a fitness project's scenes.

usage: .venv/Scripts/python.exe tools/fitness_sfx.py <project>   -> projects/<project>/audio/sfx.wav
All sounds are generated here from noise and sine waves (no third-party samples).
"""
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fitness.project import Project  # noqa: E402
from fitness.audio import beats  # noqa: E402

SR = 48000
rng = np.random.default_rng(7)


def env(n, attack, release):
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1) if attack else np.ones(n)
    return a * np.exp(-np.maximum(t - attack, 0) / release)


def lowpass_sweep(x, f0, f1):
    """One-pole low-pass whose cutoff glides from f0 to f1."""
    out = np.empty_like(x)
    fc = np.geomspace(f0, f1, len(x))
    alpha = 1 - np.exp(-2 * np.pi * fc / SR)
    y = 0.0
    for i, v in enumerate(x):
        y += alpha[i] * (v - y)
        out[i] = y
    return out


def whoosh(d=0.5):
    n = int(SR * d)
    x = lowpass_sweep(rng.standard_normal(n), 250, 4000)
    x -= lowpass_sweep(x, 120, 600)  # thin out the rumble
    shape = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return 0.9 * x * shape / (np.abs(x).max() + 1e-9)


def boom(d=0.7, f0=95, f1=42):
    n = int(SR * d)
    f = np.geomspace(f0, f1, n)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.003, 0.22)
    click = lowpass_sweep(rng.standard_normal(n), 3000, 400) * env(n, 0.0005, 0.02)
    return 0.95 * (tone + 0.6 * click)


def punch(d=0.25):
    n = int(SR * d)
    f = np.geomspace(140, 60, n)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.05)
    slap = lowpass_sweep(rng.standard_normal(n), 5000, 800) * env(n, 0.0003, 0.012)
    return 0.9 * (tone + 0.8 * slap)


def pop(d=0.09, f=880):
    n = int(SR * d)
    t = np.arange(n) / SR
    return 0.5 * np.sin(2 * np.pi * f * t * (1 + 0.5 * np.exp(-t / 0.01))) * env(n, 0.001, 0.025)


def beep(f=1250):
    n = int(SR * 0.09)
    t = np.arange(n) / SR
    one = 0.35 * np.sin(2 * np.pi * f * t) * env(n, 0.002, 0.04)
    gap = np.zeros(int(SR * 0.07))
    return np.concatenate([one, gap, one])


def main(name):
    project = Project(name) if not hasattr(Project, "load") else Project.load(name)
    starts, t = {}, 0.0
    for seg in project.segments:
        starts[seg["id"]] = t
        t += project.state["scenes"][seg["id"]]["seconds"]
    total = t
    track = np.zeros(int(SR * (total + 1)))
    events = []

    def put(sound, at, gain_db):
        i = int(at * SR)
        s = sound * 10 ** (gain_db / 20)
        j = min(len(track), i + len(s))
        track[i:j] += s[: j - i]
        events.append((round(at, 2), gain_db))

    scenes = {s["segment_id"]: s for s in project.storyboard["scenes"]}
    previous_badge = None
    for seg in project.segments:
        sid, sc, t0 = seg["id"], scenes[seg["id"]], starts[seg["id"]]
        b = beats(project, seg)
        at = lambda k: t0 + b[min(k, len(b) - 1)]
        # Whoosh into chapter changes, title cards, split screens and plans (lands on the cut).
        if any(k in sc for k in ("tag", "title", "split", "plan")):
            put(whoosh(), max(0, t0 - 0.3), -14)
        badge = (sc.get("badge") or {}).get("title")
        if badge and badge != previous_badge:
            put(pop(), t0 + 0.05, -16)
        previous_badge = badge
        if "bars" in sc:
            put(boom(), at(sc["bars"].get("beat", 1)), -12)
        if "timer" in sc:
            put(beep(), at(sc["timer"].get("beat", 0)), -18)
    # Hand-placed punches on the hook and the snap-punch moments.
    for sid, k in (("hook-1", 1), ("hook-2", 2), ("test-1", 2), ("why-6", 1), ("m5-2", 1), ("close-1", 1)):
        seg = next(s for s in project.segments if s["id"] == sid)
        put(punch(), starts[sid] + beats(project, seg)[min(k, len(beats(project, seg)) - 1)], -13)

    track = np.clip(track, -1, 1)
    stereo = (np.repeat(track[:, None], 2, axis=1) * 32767).astype(np.int16)
    out = project.path("audio/sfx.wav")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(stereo.tobytes())
    print(f"{out} {total:.2f}s {len(events)} events")


if __name__ == "__main__":
    main(sys.argv[1])
