# SPDX-License-Identifier: Apache-2.0
"""`sprite-gen prepare` hands every CLI dest to prepare.run(); prepare's own parser must know them all."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("flags", [[], ["--fit-row-scale", "--fit-strip-panel-lines", "--fit-align-x", "torso"]])
def test_cli_prepare_runs_with_the_row_fit_flags(tmp_path: Path, flags: list):
    # `sprite-gen prepare` passes every CLI dest to prepare.run(); both parsers must know them
    result = subprocess.run([sys.executable, "-m", "sprite_gen.cli", "prepare", "--out-dir", str(tmp_path / "run"),
                             "--character-id", "walker", *flags], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    fit = json.loads((tmp_path / "run/sprite-request.json").read_text()).get("fit", {})
    if flags:
        assert fit["row_scale"] is True and fit["strip_panel_lines"] is True and fit["align_x"] == "torso"


@pytest.mark.parametrize("cli_description", [None, "from the flag"])
def test_request_description_reaches_the_character(tmp_path: Path, cli_description):
    # A request built by a game's own tooling carries the look as a top-level `description`;
    # it must reach the row prompts instead of being dropped (--description still wins)
    request = {"description": "a talisman master in jade robes", "states": {"walk": {"frames": 4, "fps": 8, "action": "walk"}}}
    args = [sys.executable, "-m", "sprite_gen.cli", "prepare", "--out-dir", str(tmp_path / "run"),
            "--character-id", "alu", "--request-json", json.dumps(request)]
    if cli_description:
        args += ["--description", cli_description]
    result = subprocess.run(args, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "dropped top-level" not in result.stderr
    expected = cli_description or request["description"]
    character = json.loads((tmp_path / "run/sprite-request.json").read_text())["character"]
    assert character["description"] == expected
    assert f"Character: {expected}." in (tmp_path / "run/prompts/walk.txt").read_text()


def test_re_prepare_accepts_the_runs_own_base_image(tmp_path: Path):
    # `prepare --force --base-image <run>/base-source.png` refreshes guides and prompts in place
    from PIL import Image
    base = tmp_path / "base.png"
    Image.new("RGBA", (64, 96), (40, 80, 160, 255)).save(base)
    run = tmp_path / "run"
    first = [sys.executable, "-m", "sprite_gen.cli", "prepare", "--out-dir", str(run), "--character-id", "walker",
             "--base-image", str(base)]
    assert subprocess.run(first, text=True, capture_output=True).returncode == 0
    again = [sys.executable, "-m", "sprite_gen.cli", "prepare", "--out-dir", str(run), "--character-id", "walker",
             "--base-image", str(run / "base-source.png"), "--force"]
    result = subprocess.run(again, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (run / "base-source.png").read_bytes() == base.read_bytes()
