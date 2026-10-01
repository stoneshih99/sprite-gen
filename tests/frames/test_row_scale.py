# SPDX-License-Identifier: Apache-2.0
"""Shared non-pixel row scaling keeps pose proportions consistent."""

from PIL import Image

from sprite_gen.frames.extract import (
    extract_component_frames,
    extract_component_images,
    fit_to_cell,
)


def _different_pose_strip() -> Image.Image:
    strip = Image.new("RGBA", (180, 72), (0, 0, 0, 0))
    # Wide, short pose with its bottom contact far right; the second pose is tall.
    for y in range(10, 42):
        for x in range(5, 61):
            strip.putpixel((x, y), (200, 80, 40, 255))
    for y in range(42, 50):
        for x in range(55, 61):
            strip.putpixel((x, y), (200, 80, 40, 255))
    for y in range(5, 65):
        for x in range(105, 135):
            strip.putpixel((x, y), (40, 100, 200, 255))
    return strip


def _bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getbbox()
    assert bbox is not None
    return bbox


def test_row_scale_uses_one_safe_downscale_and_keeps_foot_baseline() -> None:
    strip = _different_pose_strip()
    cell_width = cell_height = 64
    margin = 8
    source = extract_component_images(strip, 2)
    assert source is not None
    frames = extract_component_frames(strip, 2, cell_width, cell_height, margin, margin,
                                     {"row_scale": True})
    assert frames is not None

    ratios = []
    for src, frame in zip(source, frames):
        sw, sh = (_bbox(src)[2] - _bbox(src)[0], _bbox(src)[3] - _bbox(src)[1])
        x0, y0, x1, y1 = _bbox(frame)
        ratios.extend(((x1 - x0) / sw, (y1 - y0) / sh))
        assert x0 >= margin and x1 <= cell_width - margin
        assert y0 >= margin and y1 <= cell_height - margin
        assert y1 == cell_height - margin
    assert _bbox(frames[0])[0] == margin  # off-center foot centroid clamps to safe edge
    assert max(ratios) - min(ratios) < 0.06
    assert max(ratios) <= 1.0


def test_row_scale_is_opt_in_and_ignored_for_pixel_unfake() -> None:
    strip = _different_pose_strip()
    source = extract_component_images(strip, 2)
    assert source is not None
    legacy = extract_component_frames(strip, 2, 64, 64, 8, 8, {})
    explicit_pixel = extract_component_frames(
        strip, 2, 64, 64, 8, 8,
        {"row_scale": True, "pixel_unfake": True},
    )
    assert legacy is not None and explicit_pixel is not None
    assert [frame.tobytes() for frame in legacy] == [
        fit_to_cell(image, 64, 64, 8, 8, {}).tobytes() for image in source
    ]
    assert [frame.tobytes() for frame in legacy] == [frame.tobytes() for frame in explicit_pixel]
