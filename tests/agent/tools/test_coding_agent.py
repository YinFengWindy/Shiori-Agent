from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.tools.coding_agent import CodingAgentTool
from agent.tools.registry import ToolRegistry
from coding_agents.models import RunStatus


def _context():
    return {"_trusted_context": {
        "role_id": "role-1",
        "thread_id": "thread-1",
        "transport_channel": "telegram",
        "transport_chat_id": "chat-1",
        "request_id": "request-1",
        "delivery_key": "delivery-1",
        "role_config_version": "version-1",
        "role_source": "passive_turn",
        "role_work_kind": "passive_turn",
        "role_context_created_at": "2026-07-16T00:00:00+08:00",
        "current_user_message": "请执行",
        "current_user_source_ref": "telegram:chat-1:1",
    }}


@pytest.mark.asyncio
async def test_start_passes_role_boundary_context_to_orchestrator() -> None:
    orchestrator = SimpleNamespace(
        start_run=AsyncMock(
            return_value=SimpleNamespace(
                task=SimpleNamespace(id="task-1"),
                run=SimpleNamespace(id="run-1", status=RunStatus.QUEUED),
                approval_id=None,
                reused=False,
            )
        )
    )
    tool = CodingAgentTool(orchestrator)

    payload = json.loads(
        await tool.execute(
            action="start",
            repository="D:/Coding/Demo",
            task="修复登录",
            mode="execute",
            **_context(),
        )
    )

    assert payload == {
        "task_id": "task-1",
        "run_id": "run-1",
        "status": "queued",
        "approval_id": None,
        "reused": False,
    }
    call_context = orchestrator.start_run.await_args.kwargs["context"]
    assert call_context.manager_role_id == "role-1"
    assert call_context.source_channel == "telegram"


@pytest.mark.asyncio
async def test_list_is_scoped_to_current_role_and_thread() -> None:
    orchestrator = SimpleNamespace(list=MagicMock(return_value=[]))
    tool = CodingAgentTool(orchestrator)

    await tool.execute(action="list", **_context())

    orchestrator.list.assert_called_once_with(
        manager_role_id="role-1",
        thread_id="thread-1",
    )


@pytest.mark.asyncio
async def test_missing_request_boundary_is_rejected() -> None:
    tool = CodingAgentTool(SimpleNamespace())

    with pytest.raises(ValueError, match="受信工具上下文"):
        await tool.execute(action="list", role_id="role-1", thread_id="thread-1")


@pytest.mark.asyncio
async def test_model_arguments_cannot_override_trusted_role_context() -> None:
    orchestrator = SimpleNamespace(list=MagicMock(return_value=[]))
    registry = ToolRegistry()
    registry.register(CodingAgentTool(orchestrator))
    trusted = _context()["_trusted_context"]
    registry.set_context(**trusted)

    await registry.execute(
        "coding_agent",
        {
            "action": "list",
            "role_id": "other-role",
            "thread_id": "other-thread",
            "request_id": "forged-request",
        },
    )

    orchestrator.list.assert_called_once_with(
        manager_role_id="role-1",
        thread_id="thread-1",
    )
