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
