# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Video Workflow Kit (Claude Desktop / Claude Code)

@AGENTS.md

- Skills live in `.agents/skills/`. Each `.claude/skills/<name>/SKILL.md` is a pointer, so Claude Code finds them; always follow the canonical file it names.
- The person using this kit may be non-technical. Answer in their language and give one concrete next step at a time.
  - Prefer the double-click launchers at the kit root: `1-Cai-dat.cmd` (install), `2-Nhap-key.cmd` (hidden key entry), `3-Kiem-tra.cmd` (check), `4-Dang-nhap-Codex.cmd` (optional ChatGPT login for images).
- Run kit Python as `.venv/Scripts/python.exe ...` and PowerShell scripts as `powershell -ExecutionPolicy Bypass -File ...`. Do not install tools globally beyond what `setup/setup.ps1` does.
- Never type, paste or store a key for the user. Ask them to double-click `2-Nhap-key.cmd`; it saves keys to the ignored `local/secrets.env`. Never log in to Codex, Zernio or any platform on the user's behalf.
- `.claude/settings.json` denies reading `local/secrets.env` and `.env`. Check whether a key is present with `doctor`, never by opening the file.

## Commands

Run everything from the kit root.

- Tests (offline, providers simulated): `.venv/Scripts/python.exe -m unittest discover -s tests`
  - One test: `.venv/Scripts/python.exe -m unittest tests.test_fitness.<Class>.<test_name>`
  - `tests/test_fitness.py` points `FITNESS_PROJECTS_DIR`/`FITNESS_LOCAL_DIR` at a temp folder. The end-to-end render test runs only when the render runtime (`local/fitness-runtime/node_modules/playwright`) and FFmpeg are installed.
- Fitness CLI: `.venv/Scripts/python.exe tools/fitness_video.py <command> --project <name>` (`doctor`, `setup`, `channel ...`, `status`, `review/approve --gate content|media|render`, `produce`, `music`, `build`, `render`, ...). The module docstring lists every command.
- Kit health and release: `.venv/Scripts/python.exe tools/manage.py doctor | update --component <c> | package --output <zip>` (`package` uses `git archive HEAD` and refuses uncommitted tracked changes).
- video-use helpers: `powershell -ExecutionPolicy Bypass -File setup/video-use.ps1 <helper> ...` (loads secrets only in the child process).
- Publisher (TypeScript, Node 22+): build with `npm run build` in `tools/publisher`, run as `node tools/publisher/dist/cli.js`. Exact commands are in `tools/publisher/README.md`.
- After changing a vendored component, refresh its digest: `tools/lock_components.py --component <c> ...` (see `docs/MAINTAINER.md`).

## Architecture

- **Components and versioning.** `skills.lock.json` pins each component (video-use, publisher, workflow, motion-broll, fitness-explainer, codex-image) by path and SHA256. `setup/update.ps1` / `manage.py update` refuse to overwrite a component whose files were edited locally, so record edits to vendored code (`.agents/skills/video-use`, `tools/vendor/motion-broll`) as patches in `patches/` and update the lock. Setup scripts, docs and AGENTS.md ship only as a full kit release.
- **Fitness explainer pipeline** (`tools/fitness_video.py` is the CLI; the logic lives in `tools/fitness/`):
  - `common.py` holds paths (`ROOT`, `PROJECTS`, `LOCAL`, `RUNTIME`, overridable by env vars for tests), hashing and credential loading, plus `FitnessError` for operator-facing errors.
  - `channel.py` holds the per-creator profile in ignored `local/fitness/channel.json` (palette, characters, voice presets, `music`, `sfx`, `motion`) with its own approval digest.
  - `project.py` holds the per-video artifacts under `projects/<name>/` (`brief.json`, `research/`, `script.json`, `storyboard.json`, `layout.json`, `state.json`) and the three gates `content -> media -> render`. Each approval is bound to the digest of what was reviewed, so later edits make it stale. `layout.json` (positions, exact `at` timings) sits outside content approval on purpose.
  - Producing a video: `audio.py` (Genmax narration with checkpointed and reconcilable tasks) and `poses.py` (Codex images with a Gemini fallback, Gemini batch mode) produce media through `providers.py`. A transport failure after a submit counts as an uncertain outcome, so reconcile it and never resubmit.
  - Rendering: `scenes.py` builds one HTML page per scene from `templates/` (`runtime.js`, `style.css`) and captures it frame by frame with Playwright (`capture.mjs`). Components are timed to narration speech onsets (`beat: n`).
  - Mixing and checks: `music.py` (Lyria bed per video or a licensed file), `sfx.py` (cues from the creator's pack in `local/fitness/sfx/`, built by `channel sfx-pack` and placed from the scene configs) and `assemble.py` mix the audio. Ducking applies to music only; `audio/sfx.wav` is never ducked, and a hand-made file is used as it is when the channel has no pack. `qa.py` then measures the MP4 and writes a frame sheet.
  - `tools/fitness_sfx.py` is a separate script that synthesizes an SFX track. It hand-places punches on specific segment IDs (`hook-1`, `why-6`, `m5-2`, ...), so it only fits the project it was written for.
- **Editing existing footage:** video-use (vendored skill, run through `tools/run_video_use.py`), then optional motion-broll via `tools/motion_broll.py`, which renders `edit/final-motion.mp4` beside `edit/final.mp4`.
- **Publishing:** `tools/publisher/src` (`cli.ts`, `zernio-api.ts`, `state.ts`, `validation.ts`) calls Zernio REST and keeps durable per-run state in `local/`, so interrupted or partial publishes are resumed rather than repeated. Examples of the account and publish config are in `config/*.example.json`.
