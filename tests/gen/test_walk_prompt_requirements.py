# SPDX-License-Identifier: Apache-2.0
"""Walk prompt requirements apply to exact flat and declared directional walk states."""

import pytest

from sprite_gen.gen.prepare import row_prompt


def _prompt(state: str, *, frames: int, loop: bool, directions: list[str] | None = None) -> str:
    request = {
        "cell": {"width": 192, "height": 256, "safe_margin_x": 18, "safe_margin_y": 24},
        "chroma_key": {"name": "cyan", "hex": "#00FFFF"},
        "character": {"id": "prompt-test", "description": ""},
        "style": "hand-drawn style",
    }
    if directions is not None:
        request["directions"] = {"set": directions, "mirror": {}, "anchor_suffix": "idle"}
    return row_prompt(
        request,
        state,
        {"frames": frames, "loop": loop, "action": "walking"},
    )


@pytest.mark.parametrize("direction", ["down", "up", "side"])
def test_declared_eight_frame_walk_has_biped_phases_and_loop_seam(direction: str) -> None:
    prompt = _prompt(f"{direction}_walk", frames=8, loop=True, directions=[direction])

    assert "Use distinct gait poses that create a readable cycle" in prompt
    assert "final frame flow smoothly back into the first" in prompt
    assert "frame 1 first-side contact/support, frame 2 down/compression, frame 3 passing, frame 4 up/rise, frame 5 opposite-side contact/support, frame 6 down/compression, frame 7 passing, frame 8 up/rise" in prompt
    assert "For other anatomies, adapt the support and limb sequence naturally" in prompt


def test_exact_flat_walk_gets_walk_requirements() -> None:
    prompt = _prompt("walk", frames=6, loop=True)

    assert "Use distinct gait poses that create a readable cycle" in prompt
    assert "final frame flow smoothly back into the first" in prompt
    assert "For an 8-frame loop with a two-legged character" not in prompt


def test_declared_custom_suffix_does_not_inherit_walk_requirements() -> None:
    prompt = _prompt("down_walk_custom", frames=8, loop=True, directions=["down"])

    assert "Lock the whole row to facing the viewer" in prompt
    assert "Use distinct gait poses that create a readable cycle" not in prompt
    assert "final frame flow smoothly back into the first" not in prompt


def test_undeclared_direction_walk_does_not_inherit_walk_requirements() -> None:
    prompt = _prompt("down_walk", frames=8, loop=True, directions=["up"])

    assert "Use distinct gait poses that create a readable cycle" not in prompt
    assert "final frame flow smoothly back into the first" not in prompt


def test_non_loop_walk_has_no_return_to_first_requirement() -> None:
    prompt = _prompt("side_walk", frames=8, loop=False, directions=["side"])

    assert "Use distinct gait poses that create a readable cycle" in prompt
    assert "final frame flow smoothly back into the first" not in prompt
    assert "For an 8-frame loop with a two-legged character" not in prompt


def test_other_looped_frame_count_gets_seam_without_eight_phase_order() -> None:
    prompt = _prompt("side_walk", frames=6, loop=True, directions=["side"])

    assert "final frame flow smoothly back into the first" in prompt
    assert "For an 8-frame loop with a two-legged character" not in prompt


def test_other_states_keep_their_requirements_without_walk_rules() -> None:
    prompt = _prompt("jump", frames=6, loop=False)

    assert "Show the jump through pose and vertical body position only" in prompt
    assert "Use distinct gait poses that create a readable cycle" not in prompt
    assert "final frame flow smoothly back into the first" not in prompt
