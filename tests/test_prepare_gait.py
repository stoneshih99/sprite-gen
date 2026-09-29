# SPDX-License-Identifier: Apache-2.0
"""A declared ground-contact gait reaches the run, its guide marks and its prompt; nothing else changes."""

import json
from pathlib import Path

from PIL import Image

from conftest import run_script
from sprite_gen.gen.prepare import GUIDE_FOOT

FOOT_RGB = tuple(int(GUIDE_FOOT[i:i + 2], 16) for i in (1, 3, 5))


def _prepare(out_dir: Path, walk: dict, *extra: str):
    request = {"states": {"walk": walk}}
    return run_script("prepare_sprite_run.py", "--out-dir", str(out_dir), "--character-id", "walker",
                      "--cell-width", "256", "--cell-height", "192", "--request-json", json.dumps(request), *extra)


def _colours(path: Path) -> set:
    with Image.open(path) as guide:
        return {colour for _count, colour in guide.getcolors(maxcolors=4096)}


def test_declared_gait_is_carried_marked_and_prompted(tmp_path: Path):
    walk = {"frames": 6, "fps": 13, "loop": True, "action": "walk", "gait": {"ground_travel": 120}}
    result = _prepare(tmp_path / "run", walk)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dropped states.walk" not in result.stderr
    emitted = json.loads((tmp_path / "run/sprite-request.json").read_text())
    assert emitted["states"]["walk"]["gait"] == {"ground_travel": 120.0, "steps": 2, "tolerance": 0.25, "min_frame_ms": 40.0}
    assert FOOT_RGB in _colours(tmp_path / "run/references/layout-guides/walk.png")
    prompt = (tmp_path / "run/prompts/walk.txt").read_text()
    assert "Ground contact" in prompt
    assert "about 20 px of a 256 px slot" in prompt
    assert "foot marks" in prompt


def test_undeclared_rows_keep_the_geometry_only_guide(tmp_path: Path):
    result = _prepare(tmp_path / "run", {"frames": 6, "fps": 13, "loop": True, "action": "walk"})
    assert result.returncode == 0, result.stdout + result.stderr
    emitted = json.loads((tmp_path / "run/sprite-request.json").read_text())
    assert "gait" not in emitted["states"]["walk"]
    assert FOOT_RGB not in _colours(tmp_path / "run/references/layout-guides/walk.png")
    assert "Ground contact" not in (tmp_path / "run/prompts/walk.txt").read_text()


def test_invalid_gait_fails_before_output(tmp_path: Path):
    walk = {"frames": 6, "fps": 13, "action": "walk", "gait": {"ground_travel": 120, "steps": 4}}
    result = _prepare(tmp_path / "run", walk)
    assert result.returncode != 0
    assert "must divide" in result.stderr
