# SPDX-License-Identifier: Apache-2.0
"""Ground-contact gait: planted feet must slide back as far as the game moves the sprite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from conftest import run_script
from sprite_gen.spec.gait import measure_gait, normalize_gait, planted_marks

CELL_W, CELL_H, GROUND = 256, 192, 174
TRAVEL = 120.0  # 20 px per frame over 6 frames
GAIT = {"ground_travel": TRAVEL, "steps": 2, "tolerance": 0.25}


def _walker(feet: list[float | None], width: int = CELL_W, height: int = CELL_H, ground: int = GROUND) -> Image.Image:
    """A centred torso with one 20 px sole per grounded foot (x = sole centre); None = foot lifted."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    centre = width // 2
    draw.rectangle([centre - 15, ground - 150, centre + 14, ground - 30], fill=(200, 60, 40, 255))
    for x in feet:
        if x is None:
            draw.rectangle([centre - 10, ground - 40, centre + 9, ground - 25], fill=(60, 40, 30, 255))
        else:
            draw.rectangle([round(x) - 10, ground - 20, round(x) + 9, ground - 1], fill=(60, 40, 30, 255))
    return image


def _even_walk() -> list[Image.Image]:
    """Each foot is planted for 4 frames stepping back 20 px, lifted for 2; the feet are half a loop apart."""
    stance = [158, 138, 118, 98, None, None]
    return [_walker([stance[i], stance[(i + 3) % 6]]) for i in range(6)]


def test_normalize_fills_defaults_and_rejects_bad_contracts() -> None:
    assert normalize_gait("walk", {"ground_travel": 120}, 6) == {
        "ground_travel": 120.0, "steps": 2, "tolerance": 0.25, "min_frame_ms": 40.0}
    with pytest.raises(SystemExit, match="unknown key"):
        normalize_gait("walk", {"ground_travel": 120, "speed": 4}, 6)
    with pytest.raises(SystemExit, match="must divide"):
        normalize_gait("walk", {"ground_travel": 120, "steps": 4}, 6)
    with pytest.raises(SystemExit, match="ground_travel"):
        normalize_gait("walk", {"steps": 2}, 6)


def test_marks_step_back_evenly_and_hand_over_at_contact() -> None:
    marks = planted_marks(GAIT, 6)
    # 60 px step: land 30 px ahead, slide 20 px per frame; contact frames also show the trailing foot
    assert marks == [(30.0, -30.0), (10.0, None), (-10.0, None), (30.0, -30.0), (10.0, None), (-10.0, None)]


def _walk(stance: list) -> list[Image.Image]:
    """Each foot follows ``stance`` (sole x per frame, None = lifted); the feet are half a loop apart."""
    return [_walker([stance[i], stance[(i + 3) % 6]]) for i in range(6)]


def _even_walk() -> list[Image.Image]:
    return _walk([158, 138, 118, 98, None, None])


def test_even_walk_keeps_even_timing() -> None:
    # 120 px per loop at 12 fps = 240 px/s: 20 px takes 83 ms, about 4 ticks of 50 fps
    result = measure_gait(_even_walk(), GAIT, 12)
    assert result["ok"], result["problems"]
    assert result["per_frame"] == [20.0] * 6
    assert result["durations_ms"] == [83] * 6
    assert result["ticks"] == [4] * 6 and result["tick_fps"] == 50


def test_uneven_steps_are_timed_to_the_game_speed() -> None:
    # The planted foot creeps 8 px twice, then moves 44 px into the contact frame: the right total,
    # unevenly spaced. The long move stays up longest; the short ones are held to min_frame_ms.
    result = measure_gait(_walk([158, 150, 142, 98, None, None]), GAIT, 12)
    assert result["ok"], result["problems"]
    assert result["per_frame"] == [8.0, 8.0, 44.0, 8.0, 8.0, 44.0]
    assert result["durations_ms"] == [40, 40, 183, 40, 40, 183]
    assert result["ticks"] == [2, 2, 9, 2, 2, 9]


def test_feet_that_never_trade_places_fail() -> None:
    # Both soles stay put: the only "travel" is jumping from the front foot to the rear one
    result = measure_gait([_walker([98, 158])] * 6, GAIT, 12)
    assert not result["ok"]
    assert any("other foot" in problem for problem in result["problems"])


def test_a_planted_foot_moving_forward_fails() -> None:
    result = measure_gait(_walk([138, 150, 118, 98, None, None]), GAIT, 12)
    assert not result["ok"]
    assert any("moves forward" in problem for problem in result["problems"])


def test_legs_that_carry_the_body_too_little_fail() -> None:
    # The even walk covers 120 px per loop; a game moving 240 px would drag the feet along
    result = measure_gait(_even_walk(), {**GAIT, "ground_travel": 240.0}, 12)
    assert result["ratio"] == 0.5
    assert not result["ok"]


def _walk_run(run_dir: Path, frames: list[Image.Image], gait: dict | None) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {"frames": len(frames), "fps": 13, "loop": True, "action": "walk"}
    if gait is not None:
        state["gait"] = gait
    request = {
        "version": 1, "kind": "sprite-gen-request", "engine": "component-row",
        "character": {"id": "walker", "description": "", "base_image": None},
        "cell": {"shape": "rect", "width": CELL_W, "height": CELL_H,
                 "safe_margin_x": 18, "safe_margin_y": 18, "size": CELL_H, "safe_margin": 18},
        "chroma_key": {"name": "magenta", "hex": "#FF00FF", "rgb": [255, 0, 255], "selection": "explicit"},
        "states": {"walk": state}, "style": "test", "layout": "taxonomy/v1",
    }
    (run_dir / "sprite-request.json").write_text(json.dumps(request) + "\n", encoding="utf-8")
    strip = Image.new("RGB", (CELL_W * len(frames), CELL_H), (255, 0, 255))
    for index, frame in enumerate(frames):
        strip.paste(frame, (index * CELL_W, 0), frame)
    (run_dir / "raw").mkdir(exist_ok=True)
    strip.save(run_dir / "raw" / "walk.png")
    return run_dir


def _extract(run_dir: Path) -> tuple[int, dict]:
    result = run_script("extract_sprite_row_frames.py", "--run-dir", str(run_dir))
    for name in ("frames/frames-manifest.json", "extract-failure.json"):
        path = run_dir / name
        if path.is_file():
            return result.returncode, json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError(result.stdout + result.stderr)


def test_extract_fails_a_declared_row_that_shuffles(tmp_path: Path) -> None:
    code, manifest = _extract(_walk_run(tmp_path / "run", [_walker([98, 158])] * 6, {"ground_travel": TRAVEL}))
    assert code != 0
    assert any(error.startswith("walk: gait:") for error in manifest["errors"])


def test_extract_times_and_compose_repeats_a_passing_row(tmp_path: Path) -> None:
    uneven = _walk([158, 150, 142, 98, None, None])
    run_dir = _walk_run(tmp_path / "run", uneven, {"ground_travel": TRAVEL, "tolerance": 0.5})
    code, manifest = _extract(run_dir)
    assert code == 0, manifest.get("errors")
    gait = next(row for row in manifest["rows"] if row["state"] == "walk")["gait"]
    assert gait["ok"] and len(gait["ticks"]) == 6
    assert gait["ticks"][2] > gait["ticks"][0], "the long move stays up longer"

    result = run_script("compose_sprite_atlas.py", "--run-dir", str(run_dir))
    assert result.returncode == 0, result.stdout + result.stderr
    atlas = json.loads((run_dir / "sprite-sheet-alpha.report.json").read_text())
    rects = atlas["frame_layout"]["rows"]["walk"]
    animation = json.loads(json.dumps(atlas.get("animation") or {}))
    if not animation:
        animation = json.loads((run_dir / "manifest.json").read_text())["animation"]
    walk = animation["rows"]["walk"]
    # Timing is frame duplication at the tick rate: uniform durations, shared cells, no new atlas columns
    assert walk["fps"] == gait["tick_fps"]
    assert len(rects) == walk["frames"] == sum(gait["ticks"])
    assert len({(r["x"], r["y"]) for r in rects}) == 6
    assert len(set(walk["durations_ms"])) == 1
    assert walk["gait"]["ticks"] == gait["ticks"]


def test_undeclared_rows_are_never_measured(tmp_path: Path) -> None:
    code, manifest = _extract(_walk_run(tmp_path / "run", [_walker([98, 158])] * 6, None))
    assert code == 0, manifest.get("errors")
    assert "gait" not in next(row for row in manifest["rows"] if row["state"] == "walk")
