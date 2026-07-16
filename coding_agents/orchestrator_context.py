"""Trusted role-bound request context and authorization checks."""

from __future__ import annotations

from dataclasses import dataclass

from .models import CodingTask, CodingTaskRun, PermissionLevel, TaskMode


@dataclass(frozen=True)
class CodingStartContext:
    """Role/session metadata captured at the user-message boundary."""

    manager_role_id: str
    thread_id: str
    source_channel: str
    source_chat_id: str
    request_id: str
    delivery_key: str
    role_config_version: str
    role_source: str
    role_work_kind: str
    role_context_created_at: str
    current_user_message: str
    current_user_source_ref: str

    def role_metadata(self) -> dict[str, str]:
        """Return the complete trusted RoleExecutionContext envelope."""

        return {
            "role_id": self.manager_role_id,
            "role_config_version": self.role_config_version,
            "thread_id": self.thread_id,
            "transport_channel": self.source_channel,
            "transport_chat_id": self.source_chat_id,
            "request_id": self.request_id,
            "delivery_key": self.delivery_key,
            "role_source": self.role_source,
            "role_work_kind": self.role_work_kind,
            "role_context_created_at": self.role_context_created_at,
        }


@dataclass(frozen=True)
class CodingStartResult:
    """Stable response returned by the tool after task acceptance."""

    task: CodingTask
    run: CodingTaskRun
    approval_id: str | None = None
    reused: bool = False


def validate_explicit_approval(
    context: CodingStartContext,
    *,
    approval_id: str,
    accepted: bool,
    scope: str,
) -> None:
    """Require the later inbound user text to explicitly bind its decision."""

    message = context.current_user_message.casefold()
    if approval_id.casefold() not in message:
        raise PermissionError("用户消息必须明确包含当前 approval_id")
    approval_words = ("批准", "同意", "允许", "approve", "approved", "yes")
    denial_words = ("拒绝", "不同意", "deny", "denied", "no")
    expected_words = approval_words if accepted else denial_words
    if not any(word in message for word in expected_words):
        raise PermissionError("用户消息没有明确表达当前审批决定")
    if accepted and scope == "persistent" and not any(
        word in message for word in ("持久", "永久", "信任", "persistent")
    ):
        raise PermissionError("持久仓库授权必须由用户明确表达")


def validate_idempotent_replay(
    task: CodingTask,
    run: CodingTaskRun,
    context: CodingStartContext,
    *,
    repository_id: str,
    mode: TaskMode,
    request_text: str,
    profile_id: str,
    permission_level: PermissionLevel,
) -> None:
    """Reject cross-context or changed-payload reuse of a delivery key."""

    owner = (
        task.manager_role_id,
        task.thread_id,
        task.source_channel,
        task.source_chat_id,
    )
    caller = (
        context.manager_role_id,
        context.thread_id,
        context.source_channel,
        context.source_chat_id,
    )
    if owner != caller:
        raise PermissionError("delivery_key 已属于其他角色会话")
    fingerprint = (
        task.repository_id,
        task.mode,
        task.request_text,
        run.profile_id,
        run.permission_level,
    )
    requested = (
        repository_id,
        mode,
        request_text,
        profile_id,
        permission_level,
    )
    if fingerprint != requested:
        raise ValueError("delivery_key 重放参数与原始 Coding Task 不一致")


def validate_plan_confirmation(
    context: CodingStartContext,
    task: CodingTask,
) -> None:
    """Require a later user turn that explicitly confirms the discussed plan."""

    if context.request_id == task.request_id:
        raise PermissionError("方案不能在创建 Plan Task 的同一回合确认")
    message = context.current_user_message.casefold()
    if not any(
        phrase in message
        for phrase in ("确认方案", "按此方案", "按这个方案", "confirm plan")
    ):
        raise PermissionError("用户消息没有明确确认当前方案")
