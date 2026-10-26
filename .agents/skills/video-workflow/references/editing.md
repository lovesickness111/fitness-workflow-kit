# Editing and delivery

Use these notes with video-use, not as a replacement for its cut and compositing rules. Examples illustrate choices; they do not set a default length, speed, aspect ratio, subtitle style or number of motion clips.

## Already exported portrait clips with karaoke captions

This workflow starts from an existing 3:4 or 9:16 video. The requested work may be only motion, only removal of repeated/stumbled speech, or both. Preserve the existing visual design; there is no need to reframe a landscape source or redesign subtitles unless requested.

Inspect frames and subtitle streams to distinguish burned captions from a selectable subtitle track or sidecar. Do not ask for a caption file when the supplied pixels are sufficient for the requested finish. A screenshot of karaoke text is not a word-timed transcript.

- **Burned captions:** leave the EDL's new-subtitle reference absent and render without subtitle generation (`--no-subtitles`). Existing caption pixels remain in the video. Do not use `--build-subtitles` or burn a second caption layer. The renderer's subtitles-last rule only protects separately composited subtitles; it cannot recover burned caption pixels hidden by motion.
- **Track/sidecar captions:** the renderer does not automatically retain a source subtitle stream. Preserve the supplied styling and map its events onto the cut timeline deliberately. Word-highlight effects also need inspection at trimmed events; moving a whole cue's start/end alone may not preserve karaoke timing.
- **Speech timing:** reuse a cache belonging to this exact export when available. If word timing is needed for cuts or motion and no usable timing exists, obtain it once through the kit's transcription workflow with the required STT authorization. Use ASR to locate words and retakes, not to replace the visible captions. Do not invent a cached word transcript from on-screen text.

Remove requested false starts and repeated phrases by cutting picture and audio together, using word boundaries and the existing cut padding. Prefer boundaries between complete caption phrases when they also preserve the intended speech. Inspect the visible text/highlight immediately before and after each join; retain a slightly wider clean phrase when a tight cut leaves an incomplete caption or abrupt highlight. Do not delete intentional rhetorical repetition merely because the words recur. There is no need to retime burned captions separately: they move with the retained frames.

Lock the resulting cut before generating motion timings. If no speech cuts are requested, an identity EDL retaining the full supplied clip can represent the accepted input. Record which case applies. Motion remains optional, with slot timings mapped from the retained speech.

Inspect the full caption extent over each proposed motion slot, including changing line counts, highlights and pop animations. Reserve that area and the speaker's face. Prefer full-canvas alpha panels with transparent pixels over the caption area; place the graphic in remaining space. If no useful space remains, skip the graphic or resolve the layout change with the user. An opaque full-frame replacement would hide burned captions; preserving them that way requires an explicitly planned reconstruction from suitable caption assets. Keepouts are planning constraints, not automatic detection or enforcement by the current bridge.

Match motion to the actual base dimensions and frame rate. The default video-use extraction scales portrait height to 1920, preserving aspect ratio but not necessarily the input resolution (for example 1080×1440 becomes 1440×1920). If exact source dimensions are required, use an explicitly source-sized FFmpeg finishing path and verify it rather than claiming the default renderer preserves dimensions. Use the delivered portrait MP4 and correctly sized frame inspection for QA: the current vendor beat-sheet viewport and HTML review containers still assume a landscape frame.

For final review, check every removed phrase and every motion entrance/hold/exit on the delivered portrait file. Verify that the original karaoke appears once, remains visible and keeps its highlight synchronized with speech. Include the opening, ending and phone-sized readability. Record any timing or visual limitation instead of treating a successful encode as a verified result.

## Resume and plan with the material

Read `edit/project.md`, the EDL, transcript cache and existing outputs before starting work. Distinguish completed work from pending review. A request to add motion or change speed usually extends the current cut; it does not require a new transcription or a new cut plan.

Probe the source, then inspect the packed transcript and visuals at decisions. For a recorded lesson, preserve meaningful IDE demonstrations and slide transitions when the narration refers to them. A scene change or pause alone is not evidence that a passage should be removed. Identify false takes by the spoken correction and clean restart. Keep source aspect ratio and readable UI unless the user requests another delivery format.

Collect only the missing choices that affect this edit, such as full lesson versus summary, subtitles and requested speed. Bundle related questions. Propose one concrete strategy based on the footage and carry the user's approval forward; ask again only for an unresolved choice or a change outside that approval. Optional motion remains a separate, requested or agreed finish.

## Reuse the right artifacts

- Reuse word transcripts when they belong to the unchanged source. If the source has been replaced, a matching basename alone does not establish that the cache is valid.
- Keep technical corrections in the authored subtitle file without changing raw ASR timestamps. For lessons, natural phrase boundaries and a small vocabulary of names from the slides often work better than rapid word-by-word captions.
- Preserve corrected `master.ass` or `master.srt` and the EDL's `subtitles` reference. `render.py --build-subtitles` generates `master.srt` from raw transcripts and selects it instead of the EDL subtitle file. Do not use that flag during a motion-only rerender if captions were already authored or corrected.
- Reuse unchanged motion renders when their dimensions, frame rate and timing still match the locked cut. Rebuild the affected stage when its inputs change. The current renderer still extracts segments on each invocation; do not promise automatic segment caching.

## Keep the three timelines explicit

1. **Source time:** raw transcript word timestamps.
2. **Cut time:** `word.start - kept_range.start + sum(previous kept durations)`. The motion bridge creates `edited-words.srt` in this timeline.
3. **Delivery time:** for a uniform requested speed `s`, `delivery_time = cut_time / s` and `delivery_duration = cut_duration / s`.

Label timecodes in the plan and review notes. A motion slot at cut time 330 seconds appears at delivery time 300 seconds after a 1.1× finish. Do not mix source or delivery timecodes with the bridge's cut-time `in`/`out` values.

## Requested playback-speed changes

The current video-use EDL and motion bridge do not implement a speed field. Adding one to JSON does not retime the export. For a uniform speed change after a locked cut, compose motion and burn approved captions at cut speed, then retime the composed video and its audio together. This keeps the visible captions, motion and speech aligned. Preserve the base-speed master for further editing; apply the speed change once, never to an already accelerated delivery.

For example, for a 25 fps master and a requested 1.1× finish:

```powershell
ffmpeg -i "projects/<project>/edit/final-motion-pre-speed.mp4" -filter_complex "[0:v]setpts=(PTS-STARTPTS)/1.1,fps=25[v];[0:a]atempo=1.1,asetpts=PTS-STARTPTS[a]" -map "[v]" -map "[a]" -fps_mode cfr -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart "projects/<project>/edit/final-motion.mp4"
```

Replace the project, speed and output frame rate with the actual delivery choices. Use a new output path until the previous candidate is preserved. This example requires an audio stream and a speed supported by `atempo`; adapt the filter chain for other cases. Keep `edit/edl.json` and `edit/final.mp4` intact when adding the optional motion finish. If delivering sidecar subtitles, divide their timestamps by `s` as well; the cut-time sidecar is not valid for the accelerated delivery. Recheck loudness and true peak after the speed/encode pass and correct the delivered mix if needed.

## Review the delivery file

Check the actual final export, including the speed pass, rather than only `base.mp4` or the motion preview. Probe duration, dimensions, frame rate and audio; decode the file and inspect the timeline, cut boundaries, motion entrances/exits, caption placement, opening and ending. Expected duration is a useful check, with allowance for frame rounding and codec padding. If checks pass, stop optional re-rendering.

Frames and audio metrics do not establish that speech was listened to. State which review was performed and any listening limitation. Give the user the exact final MP4 with an absolute path. Record its identity and approval in `edit/project.md`; distinguish approval of a strategy from approval of a rendered file. If the file changes, record the change and whether existing authorization covers it. Do not repeat approval requests for an unchanged approved result.
