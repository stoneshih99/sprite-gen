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
    assert normalize_gait("walk", {"ground_travel": 120}, 6) == {"ground_travel": 120.0, "steps": 2, "tolerance": 0.25}
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


def test_even_walk_grips_the_ground() -> None:
    result = measure_gait(_even_walk(), GAIT)
    assert result["measured_travel"] == TRAVEL
    assert result["per_frame"] == [20.0] * 6
    assert result["ok"]


def test_planted_feet_that_never_move_slide() -> None:
    result = measure_gait([_walker([98, 158])] * 6, GAIT)
    assert result["measured_travel"] == 0
    assert not result["ok"]


def test_a_jump_at_the_contact_frame_is_a_slide_even_when_the_total_adds_up() -> None:
    # The planted foot creeps 8 px twice, then jumps 44 px into the contact frame: 60 px per step in total
    stance = [158, 150, 142, 98, None, None]
    frames = [_walker([stance[i], stance[(i + 3) % 6]]) for i in range(6)]
    result = measure_gait(frames, GAIT)
    assert result["per_frame"] == [8.0, 8.0, 0.0, 8.0, 8.0, 0.0]
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


def test_extract_fails_a_declared_row_whose_feet_slide(tmp_path: Path) -> None:
    code, manifest = _extract(_walk_run(tmp_path / "run", [_walker([98, 158])] * 6, {"ground_travel": TRAVEL}))
    assert code != 0
    assert any(error.startswith("walk: gait:") for error in manifest["errors"])


def test_extract_records_the_measurement_on_a_passing_row(tmp_path: Path) -> None:
    # Extraction may rescale the row, so only the wiring is asserted here: a generous tolerance passes
    code, manifest = _extract(_walk_run(tmp_path / "run", _even_walk(), {"ground_travel": TRAVEL, "tolerance": 0.9}))
    assert code == 0, manifest.get("errors")
    row = next(row for row in manifest["rows"] if row["state"] == "walk")
    assert row["gait"]["measured_travel"] > 0
    assert row["gait"]["ok"]


def test_undeclared_rows_are_never_measured(tmp_path: Path) -> None:
    code, manifest = _extract(_walk_run(tmp_path / "run", [_walker([98, 158])] * 6, None))
    assert code == 0, manifest.get("errors")
    assert "gait" not in next(row for row in manifest["rows"] if row["state"] == "walk")
