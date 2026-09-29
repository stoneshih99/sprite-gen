# States & Frame Counts — sprite-gen reference

> Owns: Which states to request and how many frames each · Index: [docs/README.md](README.md)

> `SKILL.md` 허브에서 분리한 시나리오 상세. 요청할 상태(state) 목록과 프레임 수를 정할 때 이 문서를 따른다.

## Simple MVP Scope

The default user promise is deliberately simple:

> A Codex user installs this skill, provides a character/base image and one or more simple actions, then receives a sprite sheet, GIF preview, and QA notes.

Do not frame the default path as game-ready humanoid locomotion. The current Codex/image-gen path is good at short readable pose changes, identity-preserving rows, chroma cleanup, atlas composition, and QA. It is not yet reliable enough to promise precise cyclic locomotion for humanoids.

Default/simple states:

- `idle` — stable default. Use 4 frames, loop true.
- `jump` — stable default as a short non-loop action. Use 4 frames, loop false.
- `attack` — stable default as a short non-loop action. Use 4 frames, loop false.
- `wave` — simple gesture, but only stable as non-loop unless the row includes a return-to-idle frame. Use 4 frames, loop false by default; use 5 frames only when the final frame intentionally returns near frame 1.
- `talk`, `blink`, `bounce`, `hurt`, `celebrate`, `magic_cast` — allowed simple candidates, but still require motion QA before pass.

Experimental states:

- `walk`, `run`, `frontwalk`, `45_frontwalk`, and other cyclic locomotion.
- Directional cycles that require exact foot-contact alternation or phase symmetry.
- Any state where the user needs game-ready locomotion rather than a readable preview animation.

For experimental states, report them as experimental in `qa-notes.md` unless motion QA passes. Never silently promote a weak walk/run row to the same status as simple MVP output.

## Quick Path For Simple Animations

When the user asks for "simple sprite animation", prefer this request shape unless they specify otherwise:

```json
{
  "states": {
    "idle": { "frames": 4, "fps": 4, "loop": true, "action": "subtle breathing and one blink" },
    "attack": { "frames": 4, "fps": 8, "loop": false, "action": "simple windup, strike, recovery attack pose sequence with no detached effects" },
    "jump": { "frames": 4, "fps": 8, "loop": false, "action": "simple jump arc: crouch, takeoff, airborne, landing" }
  }
}
```

Add `wave` only as a non-loop gesture by default:

```json
"wave": { "frames": 4, "fps": 6, "loop": false, "action": "friendly hand wave gesture; arm changes clearly while feet stay planted" }
```

Simple MVP pass requires:

- automated extraction and atlas reports pass
- `qa/<state>.gif` reads as the requested simple action
- loop seam passes for looped states
- non-loop states have clear start/middle/end pose progression
- `qa-notes.md` records `pass`, `best-effort`, or `experimental` per state

## Frame Count Guidance

Keep default simple actions short. More frames do not automatically create smoother animation in the current component-row image generation path:

- `4` frames is the default stable range for simple actions.
- `5` frames is acceptable when a non-loop gesture needs a return-to-idle pose.
- `6` frames is the conservative upper edge for simple humanoid one-shot defaults.
- `8` frames is hatch-pet-style advanced territory, not forbidden. Use it for compact mascots, locomotion rows, or explicit experiments only when extraction/motion QA passes.
- `9` and `12` frames are **not** default simple settings. In validation runs, they increased duplicate bodies, empty/sparse frames, slot collapse, and extraction failure before adding useful in-betweens.

If a user asks for 9 or 12 frames, run it as an explicit experiment and report `duplicate-heavy`, `blur/merge`, or `extract-fail` honestly instead of treating it as a normal pass.

## Ground-Contact Gait

A walk or run row is drawn in place: the body stays on the slot centre and the game moves the sprite. The feet only read as gripping the ground when the planted foot slides backward, relative to the body, by exactly the distance the game moves the sprite in that time. Image models get leg alternation right far more often than that spacing — a row can alternate cleanly and still skate, the planted foot creeping 5 px in one frame and jumping 44 px into the next contact. Guide marks alone do not fix it: fumo regenerated three walk rows against them twice and the spacing stayed as uneven.

Declare the travel on the state:

```json
"walk": { "frames": 6, "fps": 13, "loop": true, "action": "...",
          "gait": { "ground_travel": 118, "steps": 2, "tolerance": 0.25, "min_frame_ms": 40 } }
```

- `ground_travel` (required): final cell pixels the sprite moves in the game during one loop at the state's `fps`, i.e. speed × pixels-per-unit × frames ÷ fps.
- `steps`: foot contacts per loop, `2` for a biped. `frames` must be a multiple of it. Default `2`.
- `tolerance`: allowed relative error of the tracked travel. Default `0.25`.
- `min_frame_ms`: shortest time a frame stays up after retiming. Default `40`.

What it changes:

- **Prepare** draws a ground line on the guide's bottom safe edge and one orange mark per slot: filled where the planted sole touches down, hollow for the trailing sole on contact frames (frames 0, frames/steps, …). The leading foot lands half a step ahead of the slot centre and the mark moves back `ground_travel / frames` every frame. The row prompt tells the model to put the planted foot on its mark and never to draw the marks.
- **Extract** tracks the planted foot after fit. The soles are the opaque runs in the lowest 4 px of the loop. On a contact frame the planted foot is the front sole; after it, the nearest sole behind (or, when none is, just ahead); into the next contact it is the rear sole. The row fails with `<state>: gait: …` and is not published when the tracked loop is off `ground_travel` by more than the tolerance, when a planted foot moves forward more than 3 px, or when one frame covers more than 85 % of a step (that is the other foot: legs that never trade places). Otherwise each frame gets (its travel ÷ game speed), at least `min_frame_ms`, as whole ticks of 50 fps. The manifest row records `gait` (`per_frame`, `durations_ms`, `ticks`, `tick_fps`, `measured_travel`, `ratio`, `problems`).
- **Compose-atlas** plays that timing by frame duplication, the contract for per-frame timing: an uncurated gait row repeats frame *i* `ticks[i]` times at `fps` 50. Cells are shared, so the atlas does not grow and `durations_ms` stays uniform; `animation.rows.<state>.gait` records the source timing. A curated row keeps the human order and timing.
- **Preview** (`preview_animation.py`) plays `qa/<state>.gif` with the measured per-frame durations, so review matches the game.

On fumo's walk rows (13 fps, 118 px): old rows whose legs never traded places fail (0.52x; a foot moving forward; a 70 px "step"), and the regenerated rows pass with frame times from 40 to 172 ms.

Rows without `gait` keep the geometry-only guide and are never measured or retimed. Implementation: `sprite_gen/spec/gait.py`.

## Related

- [`../SKILL.md`](../SKILL.md) — canonical behavior contract
- [`directional-anchor-workflow.md`](directional-anchor-workflow.md) — 방향성/45도/locomotion 상태의 앵커 체인
- [`qa-motion.md`](qa-motion.md) — motion continuity 판정 기준
