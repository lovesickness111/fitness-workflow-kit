# Video Workflow Kit

Windows workspace for editing existing video with video-use and publishing via Zernio REST API. Read `.agents/skills/video-workflow/SKILL.md` for end-to-end tasks. Read `START-HERE.md` for installation.

- Resolve all paths from this repository, never from the original author's machine. Keep media and outputs in `projects/<project>/`, credentials and publish checkpoints in ignored `local/`.
- Use `.venv/Scripts/python.exe` for video-use helpers through `setup/video-use.ps1`. Credentials are loaded in that child process from `local/secrets.env`; never create a secret inside the skill directory.
- After an approved video-use cut, optional motion graphics use `.agents/skills/motion-broll/SKILL.md` and `tools/motion_broll.py`. Reuse cached word transcripts, preserve `edit/edl.json` and `edit/final.mp4`, and render a separate `edit/final-motion.mp4` for review. Do not run motion setup or generate graphics by default.
- New generated fitness explainers (no source footage) use `.agents/skills/fitness-explainer/SKILL.md` and `tools/fitness_video.py`: content, media and render approvals bound to digests, Genmax narration preferred over Gemini TTS, Gemini poses from the approved channel character, outputs under `projects/<project>/render/`. Channel profile and character live in ignored `local/fitness/`. Resume pending Genmax tasks; reconcile uncertain submits, never resubmit them.
- Raster images for the kit come from `.agents/skills/codex-image` (Codex CLI with the user's own ChatGPT login, opened by `4-Dang-nhap-Codex.cmd`); fitness poses fall back to Gemini when Codex is unavailable. Never log in on the user's behalf.
- Do not paste keys into prompts, command arguments, logs, documentation, screenshots or Git. Ask users to run `setup/configure.ps1` themselves for masked input.
- Skill installation copies are managed by `skills.lock.json`. No automatic upstream `git pull`. Read `docs/MAINTAINER.md` before upgrading or releasing.
- Keep vendor skills and helpers together. Kit patches are recorded under `patches/`; the committed vendor snapshots already include them.
- Publishing supports the requested subset of TikTok, YouTube, Facebook and LinkedIn. Account IDs come from the colleague's Zernio account. Never use someone else's keys, account selectors, branding or posting history.
- Preview the completed video and prepare the precise caption, target account IDs and visibility settings. Execute publishing when authorized by the user for that concrete plan; do not ask again if approval already covers it. CLI confirmation flags must reflect actual authorization.
- Resume existing publish runs. Never create another run to bypass an uncertain response or duplicate-content rejection. Review/reconcile ambiguous attempts before another external write.
- Do not transcribe or publish during setup. Local readiness checks do not prove that remote API permissions, billing or platform acceptance are valid.
