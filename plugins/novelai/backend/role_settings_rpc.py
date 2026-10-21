"""Independent per-role CG settings; role editor drafts still own the switch."""

from .role_state import NovelAIRoleState


class NovelAIRoleSettingsRpc:
    """Validate and expose private CG prompt settings through plugin RPC."""

    def __init__(self, state: NovelAIRoleState) -> None:
        self._state = state

    async def get(self, payload: dict[str, object]) -> dict[str, object]:
        """Load the saved instructions for one existing role."""
        return {
            "prompt_instructions": self._state.prompt_instructions(_role_id(payload))
        }

    async def set(self, payload: dict[str, object]) -> dict[str, object]:
        """Persist only prompt instructions without changing the CG switch."""
        role_id = _role_id(payload)
        instructions = payload.get("prompt_instructions")
        if not isinstance(instructions, str):
            raise ValueError("自动场景 CG 补充要求必须是文本")
        self._state.save_prompt_instructions(role_id, instructions)
        return {"prompt_instructions": instructions}


def _role_id(payload: dict[str, object]) -> str:
    role_id = payload.get("role_id")
    if not isinstance(role_id, str) or not role_id.strip():
        raise ValueError("role_id 不能为空")
    return role_id.strip()
