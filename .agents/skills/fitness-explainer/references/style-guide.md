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

## Motion

Micro-movement only: slow zoom (Ken Burns) toward the working muscle, a subtle shake while holding a strain, pulsing red glows on the loaded tendon. Most scenes have one pose and at most two HUD components on screen at once. Cuts between scenes are hard cuts; each scene fades in from black in 0.25 s.

## Pose prompts

Describe only the action and camera angle, as concretely as a coach would:

- "doing a wall sit, back flat against a plain wall, thighs parallel to the floor, arms crossed, side view"
- "hanging from a pull-up bar with straight arms, shoulders engaged, front three-quarter view"
- "standing single-leg calf raise on the edge of a step, heel lifted high, side view"

Props (wall, bar, step) are drawn in the same grayscale ink. Avoid crowds, text, gym logos and brand clothing. The pipeline adds: the style text, pure black background, orange shorts as the only colour, the full body uncropped, and "same character as the reference".

## Image checks before media approval

- Same face, hair and build as the reference.
- Anatomy is plausible: hands, feet and joint angles; the pose is mechanically correct for the exercise.
- No text, watermark or visible rectangle edge; the processed background is pure black.
- Shorts are detected (no warning in `status`). If the model coloured other areas orange (skin, props), retake.
- Regenerate only the failing pose (`poses --retake <id>`).

## Writing

English, second person, energetic but calm coaching tone. One idea per scene. Lead with the mechanism ("tendons adapt slower than muscle"), then the action (the hold) and the dose (time, sets, frequency), with safety in the same scene as the load. Cite numbers only from `claims.json`.
