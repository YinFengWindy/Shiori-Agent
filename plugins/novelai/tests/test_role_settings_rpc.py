"""Public per-role prompt settings RPC validation and round trips."""

import pytest
from shiori_sdk.testing.roles import FakeRoles

from plugins.novelai.backend.role_settings_rpc import NovelAIRoleSettingsRpc
from plugins.novelai.backend.role_state import NovelAIRoleState


@pytest.fixture
def handlers(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    return NovelAIRoleSettingsRpc(NovelAIRoleState(roles))


async def test_prompt_settings_round_trip_multiline_and_clear(handlers):
    assert await handlers.get({"role_id": "mira"}) == {"prompt_instructions": ""}
    payload = {"role_id": "mira", "prompt_instructions": "保留猫耳\n柔和光线"}
    expected = {"prompt_instructions": payload["prompt_instructions"]}
    assert await handlers.set(payload) == expected
    assert await handlers.get({"role_id": "mira"}) == expected
    assert await handlers.set({"role_id": "mira", "prompt_instructions": ""}) == {
        "prompt_instructions": ""
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"role_id": " "},
        {"role_id": 42},
        {"role_id": "missing", "prompt_instructions": "text"},
        {"role_id": "mira"},
        {"role_id": "mira", "prompt_instructions": None},
        {"role_id": "mira", "prompt_instructions": 42},
    ],
)
async def test_invalid_prompt_settings_do_not_replace_saved_value(handlers, payload):
    await handlers.set({"role_id": "mira", "prompt_instructions": "原有要求"})
    with pytest.raises(ValueError):
        await handlers.set(payload)
    assert await handlers.get({"role_id": "mira"}) == {
        "prompt_instructions": "原有要求"
    }
