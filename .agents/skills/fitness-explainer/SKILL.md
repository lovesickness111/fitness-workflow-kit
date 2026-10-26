---
name: fitness-explainer
description: Produce a complete English fitness explainer video in the black-background manga style (grayscale muscular character cutouts, signature-colour shorts, pulsing red tendon highlights, green HUD timers/bars, kinetic phrases) from a topic, with Genmax narration, Gemini character poses, approval gates and optional Zernio publishing. Use for new generated fitness videos, not for editing existing footage.
---

# Fitness explainer

Work from the kit root and read `AGENTS.md`. This workflow is independent of video-use editing and does not import other repositories. Run every command with `.venv/Scripts/python.exe tools/fitness_video.py ...`. Run `status --project <name>` before resuming; never create another project to escape a pending task, stale approval or uncertain request.

References: [style guide](references/style-guide.md) (palette, pose prompts, layout rules) and [scene templates](references/scene-templates.md) (storyboard/layout schema). Read both before writing a storyboard.

## Setup and credentials

- Keys come from the environment, `local/secrets.env` or a kit-root `.env`. Ask the user to run `setup/configure.ps1` themselves; never put a key in a command, file you write, log or reply. If a user pastes a key into chat, do not reuse it; recommend rotating it.
- Narration uses `GENMAX_API_KEY` when present (preferred), otherwise `GEMINI_API_KEY` with a prebuilt Gemini voice (`voice.provider: auto`).
- Images follow `channel.image`: `provider: codex` draws through the local codex-image skill (`.claude/skills/codex-image`, Codex CLI logged in with ChatGPT; about 1–4 Codex credits per image), with `fallback: gemini` (`GEMINI_API_KEY`) when Codex is missing, logged out, refuses or fails.
  - Each pose record states `made_by` and any `fallback_reason`; report them at the media gate.
  - Codex renders 1:1, 3:2 or 2:3 only; other aspects are centre-cropped from the nearest size.
  - The codex-image skill is part of the kit; customers without Codex use `provider: gemini`.
  - With Gemini as the provider, `image.batch: true` sends the first pass of all poses as one Gemini Batch job at half price.
    - It is slower: minutes to hours, with a 24 h ceiling. `poses`/`produce` wait up to `--wait-seconds`, then say to rerun later; rerunning polls the saved job and never submits a new one.
    - Retakes and `--only` stay interactive. Items the batch failed are redrawn interactively, with `batch_fallback` recorded.
    - If a submit outcome is unknown, run `poses --reconcile-batch` before anything else.
  - Keep 1K images for poses: 512 px saves a third but blurs the cross-hatching at 1080p. The provider is chosen before a request; a failure never falls back silently to the other provider.
- `setup` installs the Playwright render runtime in ignored `local/fitness-runtime/`; `doctor` checks local readiness only. Local readiness does not prove remote billing, quota or permission.

## Channel (once, before the first video)

1. `channel init`, then edit `local/fitness/channel.json`:
   - channel name, palette, fps, scene gap;
   - `characters`: id → `description`, `signature` (`{"item": "shorts", "name": "vivid royal blue", "hex": "#1A66FF"}`, or `null` for a fully grayscale character) and `references`;
   - `default_character`.
   `palette.signature` should match the main character's signature colour. Do not reuse another channel's mascot, colours or branding.
2. Voice: `channel voices [--search ...]` lists Genmax voices with preview URLs. Generating samples costs credits: get the user's go-ahead, then `channel sample --voice-id ...` for 2–4 voices (or `--gemini-voice <Name>`). Give the user the MP3 paths to listen to; you cannot hear audio. Add every voice the user keeps to `voice.presets` (`{"brian": {"voice_id": ..., "name": ..., "sample": ...}}`) and set `voice.default`. A video can use another preset with `init --voice <preset>` or `brief.voice`. The voice belongs to the media gate: switching it regenerates narration and needs a new listen, but keeps content approval.
3. Characters:
   - **User-supplied references**: `channel add-reference --character <id> --image <file> --label front|side|face`. It crops to the largest subject, so a stray mark or provider sparkle in an empty corner is left out. Never edit marks that overlap the figure. Label each image with the character it shows and drop duplicates.
   - **Otherwise generate**: `channel character --id <id> --candidates 3` (Gemini, costs a few images). Inspect `local/fitness/characters/<id>/candidates.png` with Read, show it, then `channel select --character <id> --candidate cN`.
   - Inspect the references sheet before approval. Every reference of a pose's characters is sent with each pose request (front + side + face works well).
   - Optional licensed music: `channel.music` with `path` under `local/fitness/`, `gain_db` and `provenance.source/rights`. Reuse only music whose rights the creator confirmed.
4. `channel review`, present palette, characters, voices and music. Then `channel approve --decision "<their actual reply>"`; it binds to the digest that review printed. Changing a reference, voice, palette or music makes it stale.

## One video

Approvals: `review --gate X` records the digest of what it printed. `approve --gate X --decision "<actual reply>"` binds to that digest and refuses if files changed after the review. Never approve something you have not presented.

1. **Init**: ask 9:16 or 16:9 if the user has not said; `init --project <slug> --title ... --aspect 9:16|16:9 --tag "<Topic · Format · Setting>" [--voice <preset>]`. The content review lists the heading tags and where each starts, or MISSING if there is none.
2. **Content** (write the files; nothing is generated yet):
   - `brief.json`: audience, viewer promise, target length, and `tag`.
     - The pinned tag is a heading shown small in the top-left corner after a red bar. It changes with each main idea of the video, like the headings of a document, and stays still within one idea.
     - `brief.tag` is the opening heading, for example "Grip · Full guide · At home · No gym". On the first scene of each later main idea, set `"tag": "<new heading>"`, for example "Grip · Part 2 · Fingers". It carries forward to the following scenes until another scene changes it.
     - Write 2–5 short items joined by " · " (topic, part or idea, setting). Keep the topic item the same so the series reads as one video. Change the heading only at main ideas, usually 3–6 per video and at least 10 s apart, never every scene.
     - Hide it on one scene with `"tag": false`, for example a full-screen title card.
     - Where it changes, the old line slides out and the new one slides in at the cut. The publishing notes use these headings as YouTube chapters, minus the items every heading shares. Always set the headings for new videos.
   - `research/sources.json` and `research/claims.json`: every number, percentage, physiological claim or training prescription is a claim with sources the user can check. Prefer primary research, position stands and reputable coaching bodies. Do not invent statistics; no source means no chart.
   - Put the DOI in each locator and run `research`, which resolves every DOI on Crossref and compares titles. A resolved DOI proves the paper exists, not that it supports the claim: read the abstract (Europe PMC REST works without cookies) and quote the claim precisely, with sample size where it matters.
   - `script.json`: English spoken text per segment (one segment = one scene, usually 1–3 sentences). Short, concrete, energetic coaching voice. Put delivery hints in `delivery`, never in `text`.
   - `storyboard.json`: one scene per segment in order, with poses, HUD components and kinetic phrases (see scene templates).
   - Safety: include a warning component wherever a movement loads joints, tendons, the back or blood pressure. Give no medical diagnosis or treatment advice. Phrase benefits as evidence states them.
   - `review --gate content`: show the **complete script** and each scene's visual direction in the user's language, plus claims with sources and the source check. Then `approve --gate content --decision "<actual reply>"`.
3. **Media**: `produce` runs everything below that can be automated; run a single stage only to debug it.
   - Narration: one Genmax task per segment. The task id is saved before polling, and rerunning resumes it. If a submit has an unknown outcome, run `audio --reconcile`; it adopts the matching task from Genmax history. Never resubmit blindly. `produce` flags segments whose measured beats differ from their sentence count.
   - Poses: generated in parallel and sent with every reference of their characters, then post-processed. Inspect each pose with Read: same character, plausible anatomy, mechanically correct exercise, no text/watermark, signature colour detected. Retake one bad image only (`poses --retake <pose>`).
   - Read `review/poses-grid.png` (10% grid) and write `layout.json` tendon positions and camera focus. Then `storyboard` renders `review/storyboard.png`, every scene just after each beat. Check text, overlaps, glow placement, timer/bars legibility and 9:16 safe areas there; use `stills` only for a specific moment.
   - `review --gate media` writes `review/narration.mp3`. Send the user that file, `review/poses.png` and `review/storyboard.png`. Record approval only after they listened and looked; never describe metrics or frame inspection as listening.
4. **Render**:
   - `build` renders the scenes in parallel, assembles the compressed `render/preview.mp4` (final timing and mix) and measures it: size, LUFS, peak, music level between scenes, plus a frame sheet. Act on its notes.
   - `review --gate render` repeats the measurements. Give the preview's absolute path so the user can open it (chat bridges that attach files also need the absolute path). Approve with the user's actual reply after they have watched and listened.
5. **Final**:
   - `render` writes `render/final.mp4` and `render/delivery.json`, then checks the final at its real size.
   - Report what you inspected versus what the user listened to, and the spend shown by `status` (Genmax credits, Gemini images).
   - Content edits make the content gate stale. Edits to voice, media or layout stale only the later gates.

## A complete clip

- **Length and pace**: 30–60 s means 6–10 segments of 1–2 sentences, which gives clean beats and phrases of 2–6 words. Hook (claim with a sourced number), mechanism, one or two exercises (pose + badge + timer + tendon glow), safety in the same scene as the load, one-line takeaway.
- **Poses**: 3–6 per clip, reused across consecutive scenes (zoom, focus, glows and text change per scene). Each new pose costs one Gemini image plus retakes, and every pose needs layout work.
- **One idea on screen**: at most one HUD component plus a phrase at a time. Bars replace phrases while shown and, in 9:16, must end before a timer starts.
- **Cost ahead**: Genmax charges about one credit per spoken character. State the estimate (characters, pose count) when presenting the content gate.
- **Round trips**: batch questions into the gate messages (content + voice/aspect choices; media + storyboard), and use the creator's reply verbatim as the decision.

## Reference mode (learn from an existing video)

Use this when the creator points at a video to learn from. Take its **teaching structure, pacing and illustration vocabulary**; write new words, draw with the channel's own characters, and verify facts at the primary source. Everything stays in the ignored `reference/` folder.

1. `reference --project <p> --url <youtube-url>`: metadata, chapters, description and captions, with no media download.
   - It also slices YouTube's hover-preview storyboard (about 320×180, one frame every ~5 s) into illustration frames.
   - Black frames, flat transitions and near-duplicates are dropped. Frames rich in accent colour and line art score higher.
   - It prints chapter lengths, words and pace.
   - For each study cited in the description it prints a Europe PMC lead (title, DOI/PMID). A lead is not proof: open the abstract and check the exact number before using it.
   - If YouTube rate-limits captions (HTTP 429), rerun later, or use `--subs <file>`. With no captions at all, `--transcribe` sends the creator's file to Genmax speech-to-text (paid: ask first).
2. For sharper frames cut on real scene changes, the creator downloads the video themselves; do not fetch media yourself. Then run `reference --project <p> --video <file>`, which replaces the storyboard frames.
   - Either way it writes labelled keyframe sheets `reference/keyframes-N.png`. Read them all.
   - `reference --describe` (Gemini, a few cents) adds `reference/visuals.json`: per frame the layout, pose, HUD types, on-screen text and the closest of our templates. Already-described frames are not sent again.
3. `skeleton --seconds <target> [--frames 4]` scales the chapter structure to the target length (seconds, words at our pace, segment count).
   - It attaches each chapter's most illustrated frames, spread over the chapter. When described, each frame carries the template it maps to.
   - `reference/skeleton-<s>s.png` shows one row per chapter: the plan next to its illustrations. Read it and show it at the content gate.
   - For Shorts, pick chapters instead of compressing all of them: typically the hook, one core demonstration, the rule and a takeaway.
   - Frames mapped to `other`/`diagram` (metaphors, split comparisons, tier tables) have no template yet. Show them as a static generated still with kinetic text, or skip them. Do not trace their artwork.
4. Write brief, research, script and storyboard **from scratch**:
   - Map each chosen reference chapter to our scenes and their visual idea to our templates (timer, bars, badge, warning, tendon glow, title).
   - Do not reuse their frames, on-screen sentences, logos, characters, music, own tests or scales; design our own or credit them.
   - Numbers come from the papers you verified, not from the video.
5. Run `originality` before the content review. It measures shared 6-word runs with the reference transcript. Rewrite until it reports ok: under 10% of words, and no shared run of 8 or more words. `review --gate content` shows the result.
6. At the content gate, also show a short table: reference chapter → our scene, plus the visual ideas borrowed.

`notes` drafts the publishing description for every video, with or without a reference: chapters when valid, research mentioned with links, a safety note (`channel.publishing.disclaimer` to customise) and a music credit. The creator edits and approves it in the publishing step.

## Publishing

Optional and separately authorized. Read `../social-publishing/SKILL.md` and publish only the approved `render/final.mp4`. Draft title/caption (English unless the user says otherwise), destinations, privacy and AI/health disclosure settings. Resolve each platform's requirements honestly; do not add misleading labels or remove required ones. Execute only after authorization of that concrete plan; resume existing runs.

## Limits (v1)

Phrase-level kinetic text timed by measured pauses. Word-level timing is not implemented, and comma pauses may create extra beats, so check the printed beats and fix `at` in `layout.json`. No subtitles track. Music only when `channel.music` points to licensed audio with provenance; it loops from the start, and `loop_start` is not applied yet. Ducking is strong: with short scene gaps the bed can drop near silence (the check reports the level between scenes), so raise `gain_db` only with the creator's agreement. One pose image per scene; it may show several characters (`characters` in the pose). Gemini character consistency is good but not guaranteed: regenerate single poses rather than whole sets.
