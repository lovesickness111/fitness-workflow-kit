---
name: motion-broll
description: Add optional word-timed motion-graphic B-roll to an approved video-use edit in the Windows Video Workflow Kit. Use after the cut is locked, before final approval or publishing.
---

# Motion B-roll in this kit

Work from the kit root. Read `AGENTS.md`, the adjacent `../video-workflow/SKILL.md`, and the complete vendored guide at `tools/vendor/motion-broll/SKILL.md`. Before writing a clip, read `tools/vendor/motion-broll/reference/engine-api.md`. Use its examples as a quality bar. The vendor folder is a pinned upstream snapshot; do not edit it during a project.

This is an **optional finishing stage**, not an automatic edit pass. It adds selected motion-graphic cutaways or transparent panels; it does not remove stumbles, choose takes, fix audio, or infer new facts. User-approved `edit/edl.json` and `edit/final.mp4` stay intact. Reuse cached `edit/transcripts/*.json` belonging to this source. If an imported export has no word timings, follow the workflow skill's transcription/authorization guidance before using the word-timeline bridge; on-screen captions are not a substitute for that cache.

## Supplied portrait exports with existing karaoke

Read [Editing and delivery](../video-workflow/references/editing.md) for this input type. Preserve its 3:4 or 9:16 framing and caption design. If speech cleanup is requested, finish those cuts before timing motion; if motion alone is requested, the accepted full clip can be the locked cut.

Determine whether karaoke is burned into the pixels. For burned captions, add no subtitle layer and use `--no-subtitles` in the final render. Reserve the caption's full animated extent over each slot, plus the speaker's face. Prefer full-canvas transparent `panel` clips with no opaque pixels in those areas. The bridge checks panel alpha and size but does not enforce caption keepouts. An opaque `full` cutaway hides burned captions even when the compositing pipeline applies new subtitles last; do not use it as a caption-preserving finish without an agreed reconstruction. Use a separate authored subtitle file only when that is the actual input and workflow.

## Prepare the locked cut

1. Finish and review the video-use edit first. The EDL should be final, and rendering it should have produced `projects/<project>/edit/base.mp4`. If not, render the existing EDL with `setup/video-use.ps1 render.py ...` before proceeding.
2. Run `python tools/motion_broll.py setup --project <project>` once. This installs Playwright/Chromium in the ignored `projects/<project>/motion/` folder; no API key is needed.
3. Run `python tools/motion_broll.py timeline --project <project>`. This creates `motion/work/edited-words.srt` and `timeline.json` from kept word ranges on the **output timeline**. It fails if a source transcript is missing. Use `motion/plan.json` video path `../edit/base.mp4`.
4. Inspect `base.mp4` with the vendor `scripts/inspect_video.py` and read the generated word SRT with `scripts/words.py`. For a screen-recorded course, prefer a few meaningful full-frame workflow demonstrations or a panel in genuinely empty space; preserve readability of IDE and screenshots. Use the actual source aspect ratio, including 16:10; do not assume 16:9. Do not cover essential UI or the host. Agree a clip-by-clip plan with the user before creating graphics, unless the existing approval already covers that plan.

## Build and review

Follow the vendor guide's build, beats, render, preview, and page steps, replacing `$SKILL` with `tools/vendor/motion-broll` and `motion/` with `projects/<project>/motion/`. On Windows, use the kit `.venv/Scripts/python.exe` for Python scripts. For `beats.js` and `render.js`, set `NODE_PATH` in that PowerShell process to the absolute `projects/<project>/motion/node_modules` directory and `PLAYWRIGHT_BROWSERS_PATH` to the absolute `projects/<project>/motion/.cache/ms-playwright` directory. Render each clip at the base video's exact dimensions and frame rate; transparent panels must be ProRes 4444 `.mov` files. Keep all output under `motion/out/`.

The plan uses the upstream schema: `video`, `fps`, and `clips` with `id`, `in`, `out`, `kind` (`full` or `panel`), and `file`. Paths are relative to `motion/plan.json`. Example video path: `../edit/base.mp4`; example clip path: `out/01-workflow.mp4`. The kit bridge requires every rendered clip to last at least as long as its planned slot (within 50 ms); render a longer hold if necessary. Review `motion/out/preview.mp4`, `viewer.html`, and `compare.html`. The preview is not the final export. For portrait material, inspect the MP4 and frames at their actual dimensions; vendor `beats.js` still captures a 1920×1080 viewport and the HTML review containers use 16:9, so those default views alone cannot verify a portrait layout.

## Final composite

Run `python tools/motion_broll.py attach --project <project>`. It checks that the EDL still matches the planned timeline and writes `edit/edl.motion.json`, preserving existing overlays. If the cut changed, rerun `timeline` and revise/approve the motion plan; do not force stale timings.

Render the new EDL through video-use into `projects/<project>/edit/final-motion.mp4` (keep the original `final.mp4`), preserving the approved subtitle file and audio options. When the EDL already references corrected captions, run `powershell -ExecutionPolicy Bypass -File .\setup\video-use.ps1 render.py "projects/<project>/edit/edl.motion.json" -o "projects/<project>/edit/final-motion.mp4"` without `--build-subtitles`. That flag rebuilds captions from raw transcripts and bypasses the EDL's subtitle file; use it only when regeneration is intended. The renderer composites overlays before subtitles so captions remain on top.

All bridge word timings and clip windows refer to the locked cut before any playback-speed change. If the user requests a uniform speed finish, render a preserved `final-motion-pre-speed.mp4`, then retime the composed video and audio together into the delivery file. Follow [Editing and delivery](../video-workflow/references/editing.md) for the time mapping and command example; the bridge does not read an EDL speed field.

Review the final delivery across its entire timeline for timing, text, UI occlusion, audio and the actual frame dimensions. Inspect every motion slot and its return to the source, with captions visible. State whether audio was listened to or only measured. Present the exact final file and a comparison version when useful; a motion preview is not the delivery. Publish **only** the explicitly approved file, carrying forward approval that already covers it. Never infer approval from a successful render.
