"""Agent-facing tool for persisted Coding Agent orchestration."""

from __future__ import annotations

import json
from typing import Any

from coding_agents.orchestrator import CodingAgentOrchestrator, CodingStartContext

from .base import Tool


class CodingAgentTool(Tool):
    """Expose role-scoped Coding Agent actions through one explicit contract."""

    name = "coding_agent"
    description = (
        "在用户指定的 Git 仓库中规划或执行 Coding 任务。支持查询命名 Profile、启动、"
        "查看、取消、审批和确认方案；不要用 spawn 或 shell 直接启动 Codex/Claude。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["profiles", "start", "list", "cancel", "approve", "confirm_plan"],
            },
            "repository": {"type": "string"},
            "task": {"type": "string"},
            "mode": {"type": "string", "enum": ["plan", "execute"]},
            "profile_id": {"type": "string"},
            "permission_level": {
                "type": "string",
                "enum": ["read-only", "workspace-write", "full-access"],
            },
            "label": {"type": "string"},
            "depends_on_run_ids": {"type": "array", "items": {"type": "string"}},
            "plan_snapshot_id": {"type": "string"},
            "run_id": {"type": "string"},
            "approval_id": {"type": "string"},
            "decision": {"type": "string", "enum": ["approve", "deny"]},
            "scope": {"type": "string", "enum": ["once", "persistent"]},
            "task_id": {"type": "string"},
            "plan_content": {"type": "string"},
            "source_run_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action"],
    }

    def __init__(self, orchestrator: CodingAgentOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def execute(self, *, action: str, **kwargs: Any) -> str:
        context = _context_from_kwargs(kwargs)
        match action:
            case "profiles":
                return _json({"profiles": await self._orchestrator.profiles(probe=True)})
            case "start":
                existing_task_id = _optional(kwargs, "task_id")
                if existing_task_id:
                    result = await self._orchestrator.add_run(
                        context=context,
                        task_id=existing_task_id,
                        task_text=str(kwargs.get("task") or ""),
                        profile_id=_optional(kwargs, "profile_id"),
                        permission_level=str(kwargs.get("permission_level") or "workspace-write"),
                        label=str(kwargs.get("label") or ""),
                        depends_on_run_ids=tuple(kwargs.get("depends_on_run_ids") or ()),
                    )
                else:
                    result = await self._orchestrator.start_run(
                        context=context,
                        repository=_required(kwargs, "repository"),
                        task=_required(kwargs, "task"),
                        mode=_required(kwargs, "mode"),
                        profile_id=_optional(kwargs, "profile_id"),
                        permission_level=str(kwargs.get("permission_level") or "workspace-write"),
                        label=str(kwargs.get("label") or ""),
                        depends_on_run_ids=tuple(kwargs.get("depends_on_run_ids") or ()),
                        plan_snapshot_id=_optional(kwargs, "plan_snapshot_id"),
                    )
                return _json(
                    {
                        "task_id": result.task.id,
                        "run_id": result.run.id,
                        "status": result.run.status.value,
                        "approval_id": result.approval_id,
                        "reused": result.reused,
                    }
                )
            case "list":
                return _json(
                    {
                        "tasks": self._orchestrator.list(
                            manager_role_id=context.manager_role_id,
                            thread_id=context.thread_id,
                        )
                    }
                )
            case "cancel":
                run = await self._orchestrator.cancel(
                    run_id=_required(kwargs, "run_id"),
                    context=context,
                )
                return _json({"run_id": run.id, "status": run.status.value})
            case "approve":
                result = await self._orchestrator.approve(
                    context=context,
                    approval_id=_required(kwargs, "approval_id"),
                    decision=_required(kwargs, "decision"),
                    scope=str(kwargs.get("scope") or "once"),
                )
                return _json(
                    {
                        "task_id": result.task.id,
                        "run_id": result.run.id,
                        "status": result.run.status.value,
                        "approval_id": result.approval_id,
                    }
                )
            case "confirm_plan":
                return _json(
                    await self._orchestrator.confirm_plan(
                        task_id=_required(kwargs, "task_id"),
                        content=_required(kwargs, "plan_content"),
                        source_run_ids=tuple(kwargs.get("source_run_ids") or ()),
                        confirmed_by=context.source_chat_id,
                        context=context,
                    )
                )
        raise ValueError(f"未知 coding_agent action: {action}")


def _context_from_kwargs(kwargs: dict[str, Any]) -> CodingStartContext:
    trusted = kwargs.get("_trusted_context")
    if not isinstance(trusted, dict):
        raise ValueError("coding_agent 缺少受信工具上下文")
    role_id = str(trusted.get("role_id") or "").strip()
    thread_id = str(trusted.get("thread_id") or trusted.get("session_key") or "").strip()
    channel = str(trusted.get("transport_channel") or trusted.get("channel") or "").strip()
    chat_id = str(trusted.get("transport_chat_id") or trusted.get("chat_id") or "").strip()
    request_id = str(trusted.get("request_id") or "").strip()
    delivery_key = str(trusted.get("delivery_key") or request_id).strip()
    role_config_version = str(trusted.get("role_config_version") or "").strip()
    role_source = str(trusted.get("role_source") or "").strip()
    role_work_kind = str(trusted.get("role_work_kind") or "").strip()
    role_context_created_at = str(
        trusted.get("role_context_created_at") or ""
    ).strip()
    if not all(
        (
            role_id,
            thread_id,
            channel,
            chat_id,
            request_id,
            delivery_key,
            role_config_version,
            role_source,
            role_work_kind,
            role_context_created_at,
        )
    ):
        raise ValueError("coding_agent 缺少完整的角色、会话或请求边界上下文")
    return CodingStartContext(
        manager_role_id=role_id,
        thread_id=thread_id,
        source_channel=channel,
        source_chat_id=chat_id,
        request_id=request_id,
        delivery_key=delivery_key,
        role_config_version=role_config_version,
        role_source=role_source,
        role_work_kind=role_work_kind,
        role_context_created_at=role_context_created_at,
        current_user_message=str(trusted.get("current_user_message") or "").strip(),
        current_user_source_ref=str(trusted.get("current_user_source_ref") or "").strip(),
    )


def _required(values: dict[str, Any], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} 不能为空")
    return value


def _optional(values: dict[str, Any], name: str) -> str | None:
    value = str(values.get(name) or "").strip()
    return value or None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
