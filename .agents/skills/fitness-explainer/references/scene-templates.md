# Scene templates and schema

One scene per script segment, same order (`storyboard.scenes[i].segment_id == script.segments[i].id`). A scene's duration is its measured narration plus `scene_gap_seconds`, rounded up to a whole frame. Timing uses **beats**: the speech onsets measured in that segment's audio (`audio` prints them). Beat 0 is the first word; beat 1 is the first word after the first pause, usually the second sentence.

## storyboard.json (content-approved)

```json
{
  "poses": {
    "wall-sit": {"prompt": "doing a wall sit with the back flat against a wall, thighs parallel to the floor, side view", "aspect": "3:4"}
  },
  "scenes": [
    {"segment_id": "hook",
     "title": {"text": "Tendons adapt slower", "sub": "Here is the fix", "accent": [{"word": "tendons", "color": "highlight"}]},
     "text": [{"text": "Your muscles grow fast", "beat": 0}]},
    {"segment_id": "hold-1", "pose": "wall-sit", "tendons": ["patellar"], "jitter": 0.6, "zoom": [1.0, 1.08],
     "badge": {"kicker": "HOLD 1", "title": "The wall hold"},
     "timer": {"count": 45, "beat": 1, "over": 6, "label": "SECONDS"},
     "warning": {"text": "Stop if you feel sharp knee pain", "beat": 2},
     "bars": {"title": "Tendon stiffness", "items": [{"label": "Isometric", "value": 0.62, "display": "+31%", "claim_id": "c2"}], "beat": 0, "until_beat": 1},
     "text": [{"text": "Slide down the wall", "accent": [{"word": "wall", "color": "signature"}]}, {"text": "Hold for 45 seconds"}],
     "dim": 0}
  ]
}
```

| Field | Meaning |
|---|---|
| `pose` | Key in `poses`; omit for text/title-only scenes. Each pose is generated once and reused across scenes. |
| `poses.<id>.prompt` | Only the pose/action and camera angle. The style, black background, colour rule and character identity are added automatically. `aspect` defaults to 3:4 (9:16 video) or 1:1 (16:9). |
| `poses.<id>.character` / `characters` | Which channel character(s) the pose shows; default `default_character`. All their reference images are sent, and each signature colour is re-tinted exactly. |
| `tendons` | Labels of red pulsing glows; positions come from `layout.json`. They start at beat 1, or set the `tendons.at` override in layout. |
| `jitter` | 0–1 isometric strain shake (0.4–0.8 for holds, 0 for relaxed poses). |
| `zoom` | Ken Burns scale from/to over the scene (1.0→1.05–1.1). |
| `badge` | Top-left segment label: `kicker` (green pill) + `title`. Appears at 0.15 s. |
| `timer` | Green ring counting 0→`count` over `over` seconds (default: until scene end, which shows a time-lapse of a long hold). |
| `bars` | Horizontal bars; `value` 0–1 is the bar length, `display` the label (`+31%` counts up). **Every item needs `claim_id`**; sources print under the panel. Bars replace kinetic text while shown. In 9:16 they cover the timer area, so they must end (`until_beat`/`until`) by the time the timer starts. |
| `warning` | Yellow safety box near the bottom. |
| `title` | Large centred title for hook/outro/chapter scenes; kinetic text then shows below it. |
| `text` | Kinetic phrases, 2–6 words each, word-pop entry. Item *i* defaults to beat *i*; each stays until the next starts. `accent` colours words: `signature`, `highlight`, `accent`, `warning`, `ink`. |
| `dim` | Constant 0–0.8 darkening of the pose (rarely needed). |

Any component accepts `beat` (index) or `at` (seconds); `title`, `bars`, `warning` and `text` items also accept `until`/`until_beat`.

### Pinned heading tag

The heading is drawn in the top-left corner: a small red bar, then the line in uppercase, up to 60 characters.

- `brief.tag` opens the video.
- A scene with `"tag": "<line>"` starts a new main idea. The line carries forward until another scene changes it.
- Within one idea the heading is static, so it looks pinned across scene cuts.
- At the scene where it changes, the old line slides up and fades over about 0.25 s, and the new one slides in from the right. After a scene with `"tag": false`, the bar and the new line fade in together.
- When a heading is shown, the badge moves just below it. In 9:16 the info band and bars move down too.
- `"tag": false` hides it on that scene only.
- `project.tag_sections()` lists where each heading starts. The content review prints that list, and `notes` turns it into YouTube chapters when it gives at least three chapters, 10 s or more apart. Otherwise chapters come from segment-id groups.

### Illustration templates

| Field | Meaning |
|---|---|
| `poses.<id>.kind: "illustration"` | A drawing without the mascot (metaphor, anatomy, prop). `prompt` describes the subject. `colours: ["highlight"]` keeps one accent, e.g. a red tendon; everything else becomes grayscale. Add `characters` only if mascots appear. No text is drawn into images: words come from overlays. |
| `labels` | Callouts on the pose image: `[{text, x, y, color, accent, size, beat}]`, with x/y as fractions of the image. Without a pose they sit on the stage. Override positions per index in `layout.json scenes.<id>.labels.<i>`. |
| `marks` | `[{type: x\|check\|arrow, x, y, rotate, size, color, beat}]` drawn over the image (or stage). `arrow` points up; rotate in degrees. |
| `inset` | Framed close-up beside the pose: `{pose: <illustration>, label, accent, spots: [glow labels from layout.poses.<illustration>.tendons], labels, marks, beat, until}`. In 16:9 it takes the right column and pushes the phrases below it. It fades while bars or a meter show. |
| `split` | Two-panel comparison filling the stage: `{title, sub, left: {...}, right: {...}, beat}`. A panel has `label, title, pose, spots, value, caption, color, beat`. A `value` containing a digit needs `claim_id`. Not combined with `pose`. |
| `plan` | A row of pose cards: `{title, sub, items: [{pose, label, color}], stagger, beat}`. Fills the stage. |
| `table` | Tier or step table: `{title, sub, rows: [{left, right, color}], stagger, beat}`. Fills the stage. Use your own scales, never another channel's. |
| `meter` | Segmented effort meter in the info slot: `{label, value, max (10), caption, beat, until}`. Green, yellow, red as it fills; it replaces phrases while shown. |
| `holdbar` | Self-test clock in the info slot: big live seconds over one segment per second. `{label, goal (10), beat/at (panel in), run_at/run_beat (clock starts), speed (1), stop_at/stop_beat (optional fail: turns red with stop_label, default "Touch = stop"), until}`. Turns green when the goal is reached. |
| `angle` | A neon L in the info slot: the torso stroke draws, the leg swings from hanging (-90°) to each step's angle; level (0°) glows red. `{label, accent, steps: [{deg, beat/at}], beat, until}`. Use for L-sits, leg raises, hip angles. |
| `switch` | Easier / harder knob in the info slot, one line of text per side: `{steps: [{side: easy\|hard, text, accent, beat/at}], easy_label, hard_label, until}`. Replaces the "Too hard? Too easy?" lines. |
| `dose` | Stopwatch chip in the timer corner: `{main: "20–30s × 3", sets: 3, note: "REST 1 MIN", beat, until}`; the set dots light one by one. Not in the same scene as `timer`. |
| `transition` | How the scene comes in: `blur` (default, 0.22 s defocus), `swipe` (from below, vertical motion blur), `impact` (inverted manga flash + zoom-blur slam), `cut`, `fade`. The previous scene blurs out only into a blur entry. |
| `impact` | `true` = `transition: "impact"`. 3–4 per video, on the biggest lines. |

The holdbar, angle and switch panels share the info slot with bars and meter: kinetic phrases hide while one shows. Give them `until`/`until_beat` when phrases should come back in the same scene.

Full-stage components (`split`, `plan`, `table`) push kinetic phrases to the band below them. Use one per scene.

## layout.json (render-approved, tune freely)

```json
{
  "poses": {"wall-sit": {"focus": [0.52, 0.62], "tendons": {"patellar": {"x": 0.55, "y": 0.66, "rx": 0.045, "ry": 0.03, "rotate": -20}}}},
  "scenes": {"hold-1": {"timer": {"at": 2.4}, "text": {"1": {"at": 3.1}}, "pose": {"zoom": [1.0, 1.1], "jitter_at": 1.0}, "tendons": {"at": 1.2}}}
}
```

Coordinates are fractions of the processed pose image (x from the left, y from the top; `rx`/`ry` relative to image width). Find them by reading the pose image, then confirm with `stills`. Layout edits change only scene renders and the render approval.

## Layout slots

| | 9:16 (1080×1920) | 16:9 (1920×1080) |
|---|---|---|
| Pose | centre, 20–78% height | left half |
| Badge | top-left below the 8% UI band | top-left |
| Kinetic text / bars | top info band (12–21%) | right column, middle |
| Timer | top-right over the pose | top-right |
| Warning | 70–78% height (above the bottom 20% UI band) | right column, bottom |

Keep phrases short so they fit two lines at full size; the runtime shrinks long text down to 55%, but that is a sign to split it.
