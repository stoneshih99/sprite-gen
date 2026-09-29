# SPDX-License-Identifier: Apache-2.0
"""Ground-contact gait for locomotion rows: request contract, guide marks, stride check.

A walk or run row is drawn in place: the body stays on the slot centre while the
game moves the sprite. The feet only read as gripping the ground when the planted
foot slides backward, relative to the body, by exactly the distance the game moves
the sprite in that time. Image models get the leg alternation right far more often
than that spacing: a row can alternate cleanly and still skate, because the planted
foot creeps 5 px in one frame and jumps 40 px in the next.

``states.<state>.gait`` declares the travel so both ends can hold the row to it:

- ``prepare`` draws a ground line and one foot mark per slot on the layout guide,
  spaced evenly backward, and tells the model to plant a foot on each mark;
- ``extract`` tracks the planted foot frame to frame, fails the row when the loop
  does not cover the declared travel (a shuffle, legs that never trade places),
  and otherwise times each frame by how far the planted foot moved in it;
- ``compose-atlas`` plays that timing by repeating frames at ``TICK_FPS``.

Image models do not honour the marks to the pixel: across six walk rows the
planted foot still moved 5 px in one frame and 44 px in the next while the loop
total was right. Timing the frames is deterministic and keeps the drawings: a
frame whose foot moves twice as far stays up twice as long, so the foot moves at
the game's speed. ``min_frame_ms`` keeps a nearly still frame visible; that
frame slides a little instead of flashing by.

Fields (all distances in final cell pixels):

- ``ground_travel``: how far the sprite moves in the game during one loop
  (speed x pixels-per-unit x frames / fps). Required.
- ``steps``: foot contacts per loop, 2 for a biped walk or run. ``frames`` must
  be a multiple of it. Default 2.
- ``tolerance``: allowed relative error of the tracked travel. Default 0.25.
- ``min_frame_ms``: shortest time a frame stays up after retiming. Default 40.

Only declared rows are checked; a row without ``gait`` keeps the geometry-only
guide and is never measured.
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image

GAIT_KEYS = ("ground_travel", "steps", "tolerance", "min_frame_ms")
DEFAULT_STEPS = 2
DEFAULT_TOLERANCE = 0.25
DEFAULT_MIN_FRAME_MS = 40.0
# Retimed rows play at this rate; each frame repeats round(duration / tick) times,
# so per-frame timing stays frame duplication and durations_ms stays uniform.
TICK_FPS = 50
# Height of the sole band measured above the lowest opaque row of the loop.
GROUND_BAND = 4
# Forward slack for anti-aliasing and a heel rolling onto the toe.
FORWARD_SLACK = 3.0
# A planted foot covering more than this share of a step in one frame is the
# other foot: the row shuffles instead of trading legs.
MAX_STEP_SHARE = 0.85
ALPHA_SOLID = 128


def normalize_gait(state: str, raw: Any, frames: int) -> dict[str, Any]:
    """Validate a declared gait and return it with defaults filled in."""
    if not isinstance(raw, dict):
        raise SystemExit(f"states.{state}.gait must be an object")
    unknown = sorted(set(raw) - set(GAIT_KEYS))
    if unknown:
        raise SystemExit(f"states.{state}.gait has unknown key(s) {unknown}; allowed: {list(GAIT_KEYS)}")
    try:
        travel = float(raw["ground_travel"])
    except (KeyError, TypeError, ValueError):
        raise SystemExit(f"states.{state}.gait.ground_travel must be a number of cell pixels per loop")
    if not math.isfinite(travel) or travel <= 0:
        raise SystemExit(f"states.{state}.gait.ground_travel must be positive")
    steps = raw.get("steps", DEFAULT_STEPS)
    if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
        raise SystemExit(f"states.{state}.gait.steps must be a positive integer")
    if frames % steps:
        raise SystemExit(f"states.{state}.gait.steps ({steps}) must divide the frame count ({frames})")
    tolerance = float(raw.get("tolerance", DEFAULT_TOLERANCE))
    if not 0 < tolerance < 1:
        raise SystemExit(f"states.{state}.gait.tolerance must be between 0 and 1")
    min_frame_ms = float(raw.get("min_frame_ms", DEFAULT_MIN_FRAME_MS))
    if not 0 < min_frame_ms <= 1000:
        raise SystemExit(f"states.{state}.gait.min_frame_ms must be between 0 and 1000")
    return {"ground_travel": travel, "steps": steps, "tolerance": tolerance, "min_frame_ms": min_frame_ms}


def planted_marks(gait: dict[str, Any], frames: int) -> list[tuple[float, float | None]]:
    """Per frame: planted-sole x and, on contact frames, trailing-sole x, relative to the body centre.

    A step is ``ground_travel / steps`` long. The leading foot lands half a step
    ahead of the body and slides back one frame's travel per frame until the next
    contact, where it has become the trailing foot half a step behind.
    """
    travel = float(gait["ground_travel"])
    steps = int(gait.get("steps", DEFAULT_STEPS))
    per_frame = travel / frames
    step = travel / steps
    frames_per_step = frames // steps
    marks: list[tuple[float, float | None]] = []
    for index in range(frames):
        phase = index % frames_per_step
        planted = step / 2 - phase * per_frame
        marks.append((planted, -step / 2 if phase == 0 else None))
    return marks


def _sole_centres(frame: Image.Image, ground: int) -> list[float]:
    """Centres of the opaque runs in the sole band just above ``ground``."""
    alpha = frame.getchannel("A")
    width = frame.width
    top = max(0, ground - GROUND_BAND)
    solid = [any(alpha.getpixel((x, y)) >= ALPHA_SOLID for y in range(top, ground)) for x in range(width)]
    centres: list[float] = []
    start = None
    for x, filled in enumerate(solid + [False]):
        if filled and start is None:
            start = x
        elif not filled and start is not None:
            centres.append((start + x - 1) / 2)
            start = None
    return centres


def _track(soles: list[list[float]], contact: int, per_step: int, step_length: float) -> list[float]:
    """Planted-foot travel per transition, contacts at ``contact + k * per_step``.

    On a contact frame the planted foot is the front sole; after it, the nearest
    sole behind the previous position, or, when none is behind, the nearest sole up
    to half a step ahead (a foot creeping forward shows as negative travel instead
    of being skipped). Into the next
    contact frame the old foot has become the rear sole, so the transition is
    measured against that one.
    """
    count = len(soles)
    contacts = {(contact + k * per_step) % count for k in range(count // per_step)}
    position: dict[int, float] = {}
    for step in range(count):
        index = (contact + step) % count
        if index in contacts and soles[index]:
            position[index] = max(soles[index])
            continue
        previous = position.get((index - 1) % count)
        if previous is None:
            position[index] = max(soles[index]) if soles[index] else 0.0
            continue
        # The foot still behind wins (a swing foot's toe can touch down just ahead of it);
        # only when none is behind is a sole just ahead the planted foot creeping forward.
        behind = [sole for sole in soles[index] if -step_length <= sole - previous <= FORWARD_SLACK]
        ahead = [sole for sole in soles[index] if FORWARD_SLACK < sole - previous <= step_length / 2]
        position[index] = max(behind) if behind else (min(ahead) if ahead else previous)
    travel = []
    for index in range(count):
        following = (index + 1) % count
        target = min(soles[following]) if following in contacts and soles[following] else position[following]
        travel.append(round(position[index] - target, 1))
    return travel


def measure_gait(frames: list[Image.Image], gait: dict[str, Any], fps: float) -> dict[str, Any]:
    """Track the planted foot over one loop and time each frame to the game's speed.

    Contacts sit at frames 0, frames/steps, ... as the guide marks and the prompt
    ask. The row passes when the tracked loop covers ``ground_travel`` within
    ``tolerance``, no planted foot moves forward (a grounded foot only slides back
    relative to the body) and no frame covers more than ``MAX_STEP_SHARE`` of a
    step (that is the other foot: legs that never trade places). Each frame then
    stays up for (its travel / game speed), at least ``min_frame_ms``, as whole
    ticks of ``TICK_FPS``.
    """
    count = len(frames)
    travel = float(gait["ground_travel"])
    steps = int(gait.get("steps", DEFAULT_STEPS))
    tolerance = float(gait.get("tolerance", DEFAULT_TOLERANCE))
    min_frame_ms = float(gait.get("min_frame_ms", DEFAULT_MIN_FRAME_MS))
    step_length = travel / steps
    boxes = [frame.getchannel("A").point(lambda value: 255 if value >= ALPHA_SOLID else 0).getbbox() for frame in frames]
    bottoms = [box[3] for box in boxes if box]
    per_frame = [0.0] * count
    if bottoms and count >= steps:
        ground = max(bottoms)
        per_frame = _track([_sole_centres(frame, ground) for frame in frames], 0, count // steps, step_length)
    measured = sum(max(value, 0.0) for value in per_frame)
    ratio = measured / travel if travel else 0.0
    problems = []
    if abs(ratio - 1) > tolerance:
        problems.append(f"the planted foot covers {measured:.0f} px per loop but the game moves {travel:.0f} px "
                        f"({ratio:.2f}x, allowed ±{tolerance:.0%})")
    creep = [index for index, value in enumerate(per_frame) if value < -FORWARD_SLACK]
    if creep:
        problems.append(f"a planted foot moves forward after frame(s) {creep}")
    jumps = [index for index, value in enumerate(per_frame) if value > MAX_STEP_SHARE * step_length]
    if jumps:
        problems.append(f"after frame(s) {jumps} the planted foot covers more than {MAX_STEP_SHARE:.0%} of a "
                        f"{step_length:.0f} px step, so it is the other foot")
    speed = travel * fps / count if count else 0.0  # px per second in the game
    tick_ms = 1000.0 / TICK_FPS
    durations = [max(min_frame_ms, max(value, 0.0) / speed * 1000.0) if speed else min_frame_ms for value in per_frame]
    return {
        "ground_travel": round(travel, 1),
        "measured_travel": round(measured, 1),
        "ratio": round(ratio, 2),
        "per_frame": per_frame,
        "durations_ms": [round(value) for value in durations],
        "tick_fps": TICK_FPS,
        "ticks": [max(1, round(duration / tick_ms)) for duration in durations],
        "problems": problems,
        "ok": not problems,
    }


def gait_error(result: dict[str, Any]) -> str:
    """The row error for a failed measurement (callers prefix the state name)."""
    return (f"gait: {'; '.join(result['problems'])}; per frame {result['per_frame']} px — the legs do not walk the "
            f"body forward (a shuffle, or feet that never trade places). Regenerate the row with every planted "
            f"foot on its guide mark")
