# SPDX-License-Identifier: Apache-2.0
"""Row fit (fit.row_scale / align_x "torso") and fit.strip_panel_lines.

The per-frame fit anchors each frame on its own foot centroid and scales it by
its own bbox, so a stride or a thrust slides the body off the cell axis and a
reaching frame shrinks or clips. The row fit must keep the torso on the axis,
share one scale across the row, and never clip. Defaults stay per-frame.
"""

import numpy as np
from PIL import Image

from sprite_gen.frames.extract import (
    extract_slot_frames,
    fit_row_to_cells,
    fit_to_cell,
    row_fit_enabled,
    strip_panel_lines,
)

TORSO = (200, 30, 30, 255)
LIMB = (40, 40, 200, 255)
WEAPON = (30, 200, 30, 255)


def _figure(width: int, body_x: int, leg_reach: int = 0, weapon_reach: int = 0) -> Image.Image:
    """A 60px-tall figure: 12x34 torso+head block at `body_x`, two legs below it
    (the back leg stretched `leg_reach` px behind), and an optional 2px weapon
    thrust `weapon_reach` px ahead at chest height."""
    image = Image.new("RGBA", (width, 64), (0, 0, 0, 0))
    for y in range(2, 36):
        for x in range(body_x, body_x + 12):
            image.putpixel((x, y), TORSO)
    for y in range(36, 62):
        for x in range(body_x + 7, body_x + 11):  # front leg, straight down
            image.putpixel((x, y), LIMB)
        shift = round(leg_reach * (y - 36) / 25)
        for x in range(body_x + 1 - shift, body_x + 5 - shift):  # back leg, stretched behind
            image.putpixel((x, y), LIMB)
    for y in range(14, 16):
        for x in range(body_x + 12, body_x + 12 + weapon_reach):
            image.putpixel((x, y), WEAPON)
    return image


def _color_columns(cell: Image.Image, color: tuple[int, int, int, int]) -> np.ndarray:
    pixels = np.asarray(cell)
    return np.nonzero(np.all(pixels == np.array(color, dtype=np.uint8), axis=-1))[1]


def _torso_center(cell: Image.Image) -> float:
    xs = _color_columns(cell, TORSO)
    return (xs.min() + xs.max() + 1) / 2.0


ROW = [
    _figure(120, 50),                    # standing
    _figure(120, 60, leg_reach=40),      # stride: back leg far behind
    _figure(120, 20, weapon_reach=70),   # thrust: weapon far ahead
]
TORSO_ROW = {"align_x": "torso", "align_y": "bottom", "row_scale": True, "resample": "nearest"}


def test_row_fit_is_opt_in() -> None:
    assert not row_fit_enabled({})
    assert not row_fit_enabled({"align_x": "foot-centroid", "align_y": "bottom"})
    assert row_fit_enabled({"align_x": "torso"})
    assert row_fit_enabled({"row_scale": True})
    strip = Image.new("RGBA", (240, 64), (0, 0, 0, 0))
    strip.alpha_composite(_figure(120, 50), (0, 0))
    strip.alpha_composite(_figure(120, 60, leg_reach=40), (120, 0))
    default = extract_slot_frames(strip, 2, 96, 96, 8, 8, {"align_y": "bottom"})
    legacy = [fit_to_cell(strip.crop((i * 120, 0, (i + 1) * 120, 64)), 96, 96, 8, 8, {"align_y": "bottom"})
              for i in range(2)]
    assert [f.tobytes() for f in default] == [f.tobytes() for f in legacy]


def test_per_frame_fit_slides_the_body() -> None:
    cells = [fit_to_cell(image, 96, 96, 8, 8, {"align_y": "bottom", "resample": "nearest"}) for image in ROW]
    centers = [_torso_center(cell) for cell in cells]
    assert max(centers) - min(centers) > 6  # the bug this fit replaces


def test_torso_row_fit_keeps_torso_on_the_axis() -> None:
    cells = fit_row_to_cells(ROW, 96, 96, 8, 8, TORSO_ROW)
    for cell in cells:
        assert abs(_torso_center(cell) - 48.0) <= 1.0


def test_row_scale_is_shared_and_nothing_is_clipped() -> None:
    cells = fit_row_to_cells(ROW, 96, 96, 8, 8, TORSO_ROW)
    widths = {len(set(_color_columns(cell, TORSO).tolist())) for cell in cells}
    assert len(widths) == 1  # same torso width in every frame → one scale
    for cell in cells:
        alpha = np.asarray(cell.getchannel("A"))
        assert not alpha[:, :2].any() and not alpha[:, -2:].any()  # clear of both cell edges
        assert alpha[-8:].sum() == 0  # bottom safe margin kept
    weapon = _color_columns(cells[2], WEAPON)
    assert weapon.size and weapon.max() < 94  # the thrust fits instead of being cut


def test_bottom_alignment_pins_every_frame_to_the_baseline() -> None:
    cells = fit_row_to_cells(ROW, 96, 96, 8, 8, TORSO_ROW)
    bottoms = {cell.getbbox()[3] for cell in cells}
    assert bottoms == {96 - 8}


def test_strip_panel_lines_erases_borders_but_keeps_short_lines() -> None:
    strip = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    for index in range(2):
        left = index * 150
        for y in range(30, 90):
            for x in range(left + 50, left + 90):
                strip.putpixel((x, y), TORSO)
        for y in range(2, 98):  # vertical panel borders, 1px
            strip.putpixel((left + 5, y), (128, 128, 128, 255))
            strip.putpixel((left + 144, y), (128, 128, 128, 255))
        for x in range(left + 5, left + 145):  # top border, 2px
            strip.putpixel((x, 2), (128, 128, 128, 255))
            strip.putpixel((x, 3), (128, 128, 128, 255))
    for x in range(95, 135):  # a short arrow (27% of a slot) — must stay
        strip.putpixel((x, 50), WEAPON)

    cleaned, erased = strip_panel_lines(strip, 2)
    assert erased > 0
    pixels = np.asarray(cleaned)
    assert not np.all(pixels == np.array((128, 128, 128, 255), dtype=np.uint8), axis=-1).any()
    assert np.all(pixels == np.array(WEAPON, dtype=np.uint8), axis=-1).sum() == 40
    assert np.all(pixels == np.array(TORSO, dtype=np.uint8), axis=-1).sum() == 2 * 60 * 40


def test_strip_panel_lines_is_a_no_op_without_lines() -> None:
    strip = Image.new("RGBA", (120, 64), (0, 0, 0, 0))
    strip.alpha_composite(_figure(120, 50, weapon_reach=40), (0, 0))
    cleaned, erased = strip_panel_lines(strip, 1)
    assert erased == 0 and cleaned.tobytes() == strip.tobytes()
