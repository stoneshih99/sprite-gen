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
- ``extract`` measures how far the grounded sole pixels move backward across the
  loop and fails the row when that is off the declared travel.

Fields (all distances in final cell pixels):

- ``ground_travel``: how far the sprite moves in the game during one loop
  (speed x pixels-per-unit x frames / fps). Required.
- ``steps``: foot contacts per loop, 2 for a biped walk or run. ``frames`` must
  be a multiple of it. Default 2.
- ``tolerance``: allowed relative error of the measured travel. Default 0.25.

Only declared rows are checked; a row without ``gait`` keeps the geometry-only
guide and is never measured.
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image

GAIT_KEYS = ("ground_travel", "steps", "tolerance")
DEFAULT_STEPS = 2
DEFAULT_TOLERANCE = 0.25
# Height of the sole band measured above the lowest opaque row of the loop.
GROUND_BAND = 4
# A planted foot moves ``ground_travel / frames`` per frame. A match further than
# this multiple of that step is the other foot, not the same foot sliding.
SAME_FOOT_REACH = 1.5
# Forward slack for anti-aliasing and a heel rolling onto the toe.
FORWARD_SLACK = 3.0
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
    return {"ground_travel": travel, "steps": steps, "tolerance": tolerance}


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


def measure_gait(frames: list[Image.Image], gait: dict[str, Any]) -> dict[str, Any]:
    """How far the grounded soles move backward over one loop, against the declared travel.

    Each frame's soles are matched to the nearest sole behind them in the next
    frame (the loop wraps). A match further back than ``SAME_FOOT_REACH`` frames of
    travel is the other foot and does not count, so a row whose planted foot jumps
    in one frame measures short even when the loop total happens to add up: that
    jump is a visible slide.
    """
    count = len(frames)
    travel = float(gait["ground_travel"])
    tolerance = float(gait.get("tolerance", DEFAULT_TOLERANCE))
    boxes = [frame.getchannel("A").point(lambda value: 255 if value >= ALPHA_SOLID else 0).getbbox() for frame in frames]
    bottoms = [box[3] for box in boxes if box]
    per_frame_expected = travel / count if count else 0.0
    reach = SAME_FOOT_REACH * per_frame_expected
    per_frame: list[float] = []
    if bottoms:
        ground = max(bottoms)
        soles = [_sole_centres(frame, ground) for frame in frames]
        for index, current in enumerate(soles):
            following = soles[(index + 1) % count]
            best = 0.0
            for centre in current:
                behind = [centre - other for other in following if -FORWARD_SLACK <= centre - other <= reach]
                if behind:
                    best = max(best, min(behind))
            per_frame.append(round(best, 1))
    measured = sum(per_frame)
    ratio = measured / travel if travel else 0.0
    return {
        "ground_travel": round(travel, 1),
        "measured_travel": round(measured, 1),
        "ratio": round(ratio, 2),
        "per_frame": per_frame,
        "ok": abs(ratio - 1) <= tolerance,
    }


def gait_error(result: dict[str, Any], tolerance: float) -> str:
    """The row error for a failed measurement (callers prefix the state name)."""
    return (f"gait: planted feet move back {result['measured_travel']:.0f} px per loop but the game moves "
            f"{result['ground_travel']:.0f} px ({result['ratio']:.2f}x, allowed ±{tolerance:.0%}); per frame "
            f"{result['per_frame']} — the feet slide. Regenerate the row with every planted foot on its guide mark")
