# Style guide

## Look

- Canvas pure black (#000). Character in black-and-white ink: dense cross-hatching, detailed muscular anatomy and high-contrast grayscale. The look is generic gritty sports manga; never name or imitate a specific artist or series.
- Colour is reserved and meaningful:
  - **signature**: one item per character, used as identity in every scene. For example, blue shorts on the lean main character; a monochrome character has none. `palette.signature` repeats the main character's colour for keywords and accents;
  - **highlight** (#FF3B30): load, strain and warnings on the body (tendon glows, red keywords);
  - **accent** (#34C759): progress and positive results (timer ring, bars, kicker pill);
  - **warning** (#FFCC00): safety box only.
- Every video pins a short title tag top-left (red bar + "TOPIC · FORMAT · SETTING" in small uppercase). The badge sits below it.
- Typography: Montserrat Black, uppercase phrases, one or two coloured keywords per phrase at most.
- Accent words glow: every `accent` word is drawn as neon in its own colour. When it appears its core flares toward white for about 0.1 s, then it settles and breathes. The glow is the focus of the line, so colour only the one word or short phrase the viewer must catch; the rest stays white. `channel.motion.keyword_glow: false` turns it off.

## Motion

- Inside a scene, micro-movement only: slow zoom (Ken Burns) toward the working muscle, a subtle shake while holding a strain, pulsing red glows on the loaded tendon. Most scenes have one pose and at most two HUD components on screen at once.
- Between scenes, the default is a **0.22 s defocus blur**. The outgoing scene blurs over its last 0.14 s and the next one comes into focus, which reads as one soft cut, as on the reference channels. A scene's `transition` picks another entry:
  - `swipe`: rises from below with vertical motion blur. Use it in the hook, at most a few times.
  - `impact` (or `impact: true`): 3 frames of an inverted white flash with manga speed lines, then a zoom-blur slam into the scene. Reserve it for the 3–4 biggest lines of a video: the method's name, the key number, the payoff.
  - `cut`: hard cut, sharp. `fade`: the old fade from black.
  - `channel.motion.transition` or `brief.transition` sets the default.
- Pace, measured on the reference channel's recent videos (12–30 changes a minute):
  - Hook (first minute): a new picture or a big visual change every 2–4 s, 15–25 changes.
  - Body: 3–7 s per pose. A long exercise scene stays on one pose but must change something every 4–6 s (a new phrase, label, panel or glow).
  - On average something new appears every ~0.6 s in a busy scene: one phrase, a label, a mark, a panel.
- Every on-screen event has a sound when the channel has an SFX pack (see SKILL.md): never two cues within 0.12 s, the bigger event wins.

## Pose prompts

Describe only the action and camera angle, as concretely as a coach would:

- "doing a wall sit, back flat against a plain wall, thighs parallel to the floor, arms crossed, side view"
- "hanging from a pull-up bar with straight arms, shoulders engaged, front three-quarter view"
- "standing single-leg calf raise on the edge of a step, heel lifted high, side view"

Props (wall, bar, step) are drawn in the same grayscale ink. Avoid crowds, text, gym logos and brand clothing. The pipeline adds: the style text, pure black background, orange shorts as the only colour, the full body uncropped, and "same character as the reference".

Rules learned from real batches (a hundred-plus images per video):

- **Say what touches what.** End every pose prompt with its contact points: "only his hands on the chair seats, buttocks and feet in the air, nothing else touches the floor". In-between positions ("halfway down") come back floating in the air; prefer the end position or "feet planted, weight on them".
- **Nothing in front of a held leg.** In side views the model places the second chair or step in front of the legs and rests the feet on it, which is exactly the cheat the exercise forbids. Write the layout: "the two chairs stand side by side right under his hips, one under each hand, the near chair hides most of the far one; there is NO chair or object in front of his legs; his feet touch nothing".
- **Close-ups become whole figures.** "Close-up of his legs" usually returns the full body floating with no support. Ask for the full pose with its support and let the edit zoom in.
- **Spell poses joint by joint** (feet, knees, hip height, hands). Short names ("tuck", "slow sit", "rock up") are guessed wrong.
- **Two people**: "side by side with a clear gap, not overlapping", each with his own prop.
- **Head colour**: a red glow near the head turns the hair red; add "his hair stays jet black, nothing red on his head or face".

## Image checks before media approval

- Same face, hair and build as the reference.
- Anatomy is plausible: hands, feet and joint angles; the pose is mechanically correct for the exercise.
- No text, watermark or visible rectangle edge; the processed background is pure black.
- Shorts are detected (no warning in `status`). If the model coloured other areas orange (skin, props), retake.
- Nothing floats: every figure is supported by what the prompt names (floor, chairs, bar).
- Feet and legs do not rest on a prop the exercise does not use (the second chair, a step, a wall).
- Props keep the grayscale ink: brown or tinted chairs are a retake.
- Check each image against its own spoken line, not just for beauty: a correct drawing of the wrong step is still wrong. Review at full size, nine images per sheet with the line written above each; thumbnails hide these errors.
- Regenerate only the failing pose (`poses --retake <id>`), with the prompt fixed, not the same prompt again.

## Writing

English, second person, energetic but calm coaching tone. One idea per scene. Lead with the mechanism ("tendons adapt slower than muscle"), then the action (the hold) and the dose (time, sets, frequency), with safety in the same scene as the load. Cite numbers only from `claims.json`.
