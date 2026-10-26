---
name: video-workflow
description: Set up this Windows video kit, edit existing footage with video-use and publish reviewed outputs through Zernio. Use for the complete edit-to-publish workflow and local setup or recovery.
---

# Video workflow

Locate the kit root by `skills.lock.json` and `START-HERE.md`, then read its `AGENTS.md`. Use the user's language; guide nontechnical users with one concrete next step when human action is needed.

## Setup

Run `setup/setup.ps1` from the kit root when installation is needed. It installs missing Windows prerequisites via winget when available, creates an isolated Python environment, and builds the standalone publisher. On an existing workspace, inspect readiness before reinstalling. If PATH selects an old or broken Node/npm, inspect available executable paths and versions; an already installed compatible runtime can be used explicitly. Do not assume a machine-wide upgrade is necessary.

Use `setup/doctor.ps1` to report local readiness. Do not transcribe a sample or publish during setup. Ask the user to run `setup/configure.ps1` themselves in a terminal they can type into; it has masked prompts for the main and optional secondary Zernio key. Check only variable presence, never values. A tool session or a queued panel-open result does not prove the user has an interactive terminal. Login/consent on ElevenLabs, Zernio or social platforms belongs to the user.

## Edit

Create `projects/<project>/input/` and keep edit outputs under that project. Read the complete adjacent `../video-use/SKILL.md` and its relevant helpers. For resuming an edit, already exported portrait clips with karaoke captions, screen-recorded lessons, authored subtitles or playback-speed changes, also read [Editing and delivery](references/editing.md). Kit integration: invoke helpers using `setup/video-use.ps1 <helper.py> <arguments>` so the isolated Python runtime and `local/secrets.env` apply. Do not follow upstream global install or `.env` instructions; the kit has already supplied the skill and helpers. Keep skill files unchanged during editing.

For a supplied 3:4 or 9:16 export that already has karaoke captions, treat the framing and captions as existing design. Establish whether captions are burned into the pixels or supplied as a subtitle track/sidecar. Preserve them unless the user requests changes. Trim requested speech mistakes before timing motion. Burned captions survive synchronized picture/audio cuts, but cannot be restored above an opaque overlay by the renderer's subtitles-last rule; follow the caption-preserving motion guidance below and in the editing reference.

Inspect footage, reuse transcripts, agree an edit strategy and obtain authorization before rendering. Explain that ElevenLabs receives extracted audio and consumes STT quota. Source speech and a cached word-level transcript can be reused without another transcription. If the user requests music, use music they provide or establish its license, offer previews when taste matters, duck under speech and retain license notes. Do not claim to have listened when only metrics were checked.

Show the output using an absolute path to the MP4. Record edit decisions, the delivery file's duration/dimensions/frame rate/speed, the scope of user approval and remaining work in the project's `edit/project.md`. Resume from that record rather than reopening settled choices.

## Optional motion-graphic finish

After the video-use cut is approved and before publishing, offer motion B-roll only when it clarifies a few moments (for example a workflow, file transition, or comparison). Read the complete adjacent `../motion-broll/SKILL.md` and use its Windows bridge. Do not run it during setup or assume every line needs animation. It reuses the cached word-level transcript and produces a separate `edit/final-motion.mp4`, leaving the original video intact. Review the motion plan before rendering and the entire final MP4 before publishing. Record which version the user approved in `edit/project.md`.

## Publish

Read `../social-publishing/SKILL.md`. Use the existing MP4; Studio generation is not part of this kit. Select only requested platforms and verify the colleague's account IDs. Draft the title/caption and resolve destinations and privacy before the upload/validation step. Prepare the concrete plan and obtain publishing authorization unless already given for that exact plan; carry existing decisions and authorization forward. Retain run IDs and report each platform's actual status and permalink when supplied. Scheduled is not published. If interrupted, inspect and resume the recorded run.

## Update

Read `docs/MAINTAINER.md` at kit root for maintenance. For colleagues, use `setup/update.ps1` with an approved kit release tag or extracted release folder. Never update vendor directly from upstream main in daily use. Preserve local credentials, projects and publish history.
