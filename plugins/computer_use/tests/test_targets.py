"""Stale window incarnations, snapshots, tokens and coordinate spaces fail closed."""

import base64
from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from agent.tools.base import ToolResult
from plugins.computer_use.backend.targets import WindowTargets
from plugins.computer_use.backend.windows import WindowIdentity


def snapshot(number="s00000001"):
    pixels = BytesIO()
    Image.new("RGB", (300, 200)).save(pixels, format="PNG")
    return ToolResult(
        structured_content={
            "pid": 42,
            "window_id": 81,
            "snapshot_id": number,
            "elements": [{"element_token": number + ":2"}],
        },
        content_blocks=[
            {
                "image_url": {
                    "url": "data:image/png;base64,"
                    + base64.b64encode(pixels.getvalue()).decode()
                }
            }
        ],
    )


@pytest.fixture
def targets(monkeypatch):
    identity = WindowIdentity(42, 81, 123.0, (100, 100, 400, 300), 144)
    monkeypatch.setattr(
        "plugins.computer_use.backend.targets.inspect_window", lambda *_: identity
    )
    owner, result = WindowTargets(), snapshot()
    owner.remember(identity, result)
    assert result.structured_content is not None
    nonce = result.structured_content["observation_id"]
    assert nonce in result.text
    return (
        owner,
        identity,
        {
            "pid": 42,
            "window_id": 81,
            "snapshot_id": "s00000001",
            "observation_id": nonce,
        },
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"snapshot_id": "s00000000"},
        {"observation_id": "old"},
        {"element_token": "s00000001:99"},
        {"element_index": 2},
        {"x": 20},
        {"x": 300, "y": 20},
        {"x": -1, "y": 0},
        {"pid": 0},
        {"window_id": None},
    ],
)
def test_invalid_references_and_coordinates_are_rejected(targets, changes):
    owner, _, base = targets
    with pytest.raises(ValueError):
        owner.validate("click", {**base, **changes})


@pytest.mark.parametrize(
    "changes", [{"created": 124.0}, {"dpi": 192}, {"bounds": (110, 100, 410, 300)}]
)
def test_changed_process_incarnation_dpi_or_position_needs_new_snapshot(
    targets, monkeypatch, changes
):
    owner, identity, base = targets
    monkeypatch.setattr(
        "plugins.computer_use.backend.targets.inspect_window",
        lambda *_: replace(identity, **changes),
    )
    with pytest.raises(ValueError, match="身份、位置或缩放"):
        owner.validate("click", {**base, "element_token": "s00000001:2"})


def test_fresh_snapshot_invalidates_previous_tokens(targets):
    owner, identity, base = targets
    result = snapshot("s00000002")
    owner.remember(identity, result)
    base.update(
        snapshot_id="s00000002",
        observation_id=result.structured_content["observation_id"],
    )
    with pytest.raises(ValueError, match="element_token"):
        owner.validate("click", {**base, "element_token": "s00000001:2"})
    assert owner.validate("click", {**base, "element_token": "s00000002:2"}) == identity


def test_driver_restart_reusing_native_ids_does_not_accept_old_observation(targets):
    _, identity, old = targets
    successor, result = WindowTargets(), snapshot()
    successor.remember(identity, result)
    assert result.structured_content["snapshot_id"] == old["snapshot_id"]
    with pytest.raises(ValueError, match="observation_id"):
        successor.validate("click", {**old, "element_token": "s00000001:2"})


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("hotkey", {"keys": ["ctrl", "k"]}),
        ("press_key", {"key": "k", "modifiers": ["ctrl"]}),
    ],
)
def test_unreliable_background_modifiers_fail_before_native_input(
    targets, name, arguments
):
    owner, identity, base = targets
    target = {**base, **arguments}
    with pytest.raises(ValueError, match="foreground"):
        owner.validate(name, target)
    assert owner.validate(name, {**target, "delivery_mode": "foreground"}) == identity
