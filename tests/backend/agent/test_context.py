from pathlib import Path

import pytest

from agent.context import ContextBuilder, ContextRequest
from core.roles import RoleStore
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY


def test_context_builder_injects_interrupted_turn_as_separate_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class _Skills:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def get_always_skills(self) -> list[str]:
            return []

        def load_skills_for_context(self, names: list[str]) -> str:
            return ""

        def build_skills_summary(self) -> str:
            return ""

    class _Memory:
        def read_profile(self) -> str:
            return ""

        def read_self(self) -> str:
            return ""

        def read_recent_context(self) -> str:
            return ""

        def get_memory_context(self) -> str:
            return ""

    monkeypatch.setattr("agent.context.SkillsLoader", _Skills)
    monkeypatch.setattr(
        "agent.context.build_agent_static_identity_prompt", lambda **_: "identity"
    )
    monkeypatch.setattr(
        "agent.context.build_skills_catalog_prompt", lambda text: text
    )
    RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test role",
    )
    builder = ContextBuilder(tmp_path, _Memory())  # type: ignore[arg-type]
    result = builder.render(
        ContextRequest(
            history=[
                {
                    "role": "assistant",
                    "content": "partial",
                    "reasoning_content": "retain-cot",
                }
            ],
            current_message="继续",
        ),
        session_metadata={
            "role_id": "mira",
            INTERRUPTED_TURN_METADATA_KEY: {"turn_id": "turn-1"},
        },
    )

    frame = result.messages[-2]
    assert frame["role"] == "user"
    assert "上一轮助手回复因用户主动中断而未完成" in frame["content"]
    assert result.messages[-3]["reasoning_content"] == "retain-cot"
    assert "interrupted" not in result.messages[-3].get("content", "")
