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

A walk or run row is drawn in place: the body stays on the slot centre and the game moves the sprite. The feet only read as gripping the ground when the planted foot slides backward, relative to the body, by exactly the distance the game moves the sprite in that time. Image models get leg alternation right far more often than that spacing — a row can alternate cleanly and still skate, the planted foot creeping 5 px in one frame and jumping 40 px into the next contact.

Declare the travel on the state so generation and extraction both hold the row to it:

```json
"walk": { "frames": 6, "fps": 13, "loop": true, "action": "...",
          "gait": { "ground_travel": 118, "steps": 2, "tolerance": 0.25 } }
```

- `ground_travel` (required): final cell pixels the sprite moves in the game during one loop, i.e. speed × pixels-per-unit × frames ÷ fps.
- `steps`: foot contacts per loop, `2` for a biped. `frames` must be a multiple of it. Default `2`.
- `tolerance`: allowed relative error of the measured travel. Default `0.25`.

What it changes:

- **Prepare** draws a ground line on the guide's bottom safe edge and one orange mark per slot: filled where the planted sole touches down, hollow for the trailing sole on contact frames. A step is `ground_travel / steps` long; the leading foot lands half a step ahead of the slot centre and the mark moves back `ground_travel / frames` every frame. The row prompt tells the model to put the planted foot on its mark and never to draw the marks.
- **Extract** measures the row after fit: the opaque runs in the lowest 4 px of the loop are the soles, each is matched to the nearest sole behind it in the next frame (the loop wraps), and the per-frame moves add up to the measured travel. A match further back than 1.5 frames of travel is the other foot and does not count, so a planted foot that jumps into a contact frame measures short even when the loop total adds up. Outside the tolerance the row fails with a `<state>: gait: …` error and is not published; the manifest row records `gait` (`measured_travel`, `ratio`, `per_frame`) either way.

Rows without `gait` keep the geometry-only guide and are never measured. Implementation: `sprite_gen/spec/gait.py`.

## Related

- [`../SKILL.md`](../SKILL.md) — canonical behavior contract
- [`directional-anchor-workflow.md`](directional-anchor-workflow.md) — 방향성/45도/locomotion 상태의 앵커 체인
- [`qa-motion.md`](qa-motion.md) — motion continuity 판정 기준
