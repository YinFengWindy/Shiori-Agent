from __future__ import annotations

import re
from dataclasses import dataclass

from coding_agents.models import PermissionLevel, Provider, TaskMode

OUTER_SANDBOX_READ_ONLY = "shiori-read-only"
OUTER_SANDBOX_WORKSPACE_WRITE = "shiori-workspace-write"
OUTER_SANDBOX_FULL_ACCESS = "shiori-full-access"

_SECRET_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PermissionPolicyError(ValueError):
    """权限档位或审批上下文不满足运行要求。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PermissionApproval:
    """用户消息边界验证后签发的一次性权限审批上下文。"""

    approval_id: str
    run_id: str
    approved_level: PermissionLevel
    allow_network: bool = False
    secret_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EffectivePermission:
    """经过运行模式、审批和外层 sandbox 约束后的能力快照。"""

    provider: Provider
    level: PermissionLevel
    repository_read: bool
    worktree_write: bool
    run_tests: bool
    network: bool
    secret_names: frozenset[str]
    merge: bool
    push: bool
    codex_sandbox: str
    outer_sandbox_profile: str | None


class PermissionPolicy:
    """把三档产品权限映射为不可绕过的运行能力。"""

    def resolve(
        self,
        *,
        run_id: str,
        provider: Provider | str,
        mode: TaskMode | str,
        requested_level: PermissionLevel | str,
        approval: PermissionApproval | None = None,
        outer_sandbox_available: bool = False,
    ) -> EffectivePermission:
        """解析有效权限；方案阶段始终降为只读。"""
        normalized_provider = _parse_provider(provider)
        normalized_mode = _parse_mode(mode)
        requested = _parse_level(requested_level)
        level = (
            PermissionLevel.READ_ONLY
            if normalized_mode is TaskMode.PLAN
            else requested
        )
        if level is PermissionLevel.FULL_ACCESS:
            self._validate_full_access(
                run_id=run_id,
                approval=approval,
            )
        outer_profile = _resolve_outer_profile(
            normalized_provider,
            level,
            outer_sandbox_available=outer_sandbox_available,
        )
        return _effective(
            normalized_provider,
            level,
            network=approval.allow_network if approval is not None else False,
            secret_names=(approval.secret_names if approval is not None else frozenset()),
            outer_sandbox_profile=outer_profile,
        )

    def _validate_full_access(
        self,
        *,
        run_id: str,
        approval: PermissionApproval | None,
    ) -> None:
        if approval is None:
            raise PermissionPolicyError(
                "permission_denied", "full-access 必须绑定用户明确审批"
            )
        if not approval.approval_id.strip() or approval.run_id != run_id:
            raise PermissionPolicyError(
                "permission_denied", "权限审批与当前 Run 不匹配"
            )
        if approval.approved_level is not PermissionLevel.FULL_ACCESS:
            raise PermissionPolicyError(
                "permission_denied", "审批范围不包含 full-access"
            )
        if any(
            not isinstance(name, str) or not _SECRET_NAME_PATTERN.fullmatch(name.strip())
            for name in approval.secret_names
        ):
            raise PermissionPolicyError(
                "permission_denied", "审批包含无效的 Secret 环境变量名"
            )


def _effective(
    provider: Provider,
    level: PermissionLevel,
    *,
    network: bool = False,
    secret_names: frozenset[str] = frozenset(),
    outer_sandbox_profile: str | None = None,
) -> EffectivePermission:
    writable = level is not PermissionLevel.READ_ONLY
    return EffectivePermission(
        provider=provider,
        level=level,
        repository_read=True,
        worktree_write=writable,
        run_tests=writable,
        network=network if level is PermissionLevel.FULL_ACCESS else False,
        secret_names=(
            frozenset(name.strip() for name in secret_names if name.strip())
            if level is PermissionLevel.FULL_ACCESS
            else frozenset()
        ),
        merge=False,
        push=False,
        codex_sandbox=(
            "danger-full-access"
            if level is PermissionLevel.FULL_ACCESS
            else level.value
        ),
        outer_sandbox_profile=outer_sandbox_profile,
    )


def _resolve_outer_profile(
    provider: Provider,
    level: PermissionLevel,
    *,
    outer_sandbox_available: bool,
) -> str | None:
    needs_outer_sandbox = (
        provider is Provider.CLAUDE or level is PermissionLevel.FULL_ACCESS
    )
    if not needs_outer_sandbox:
        return None
    if not outer_sandbox_available:
        raise PermissionPolicyError(
            "sandbox_unavailable", "当前执行器权限需要可用的外层 sandbox runner"
        )
    return {
        PermissionLevel.READ_ONLY: OUTER_SANDBOX_READ_ONLY,
        PermissionLevel.WORKSPACE_WRITE: OUTER_SANDBOX_WORKSPACE_WRITE,
        PermissionLevel.FULL_ACCESS: OUTER_SANDBOX_FULL_ACCESS,
    }[level]


def _parse_level(value: PermissionLevel | str) -> PermissionLevel:
    try:
        return PermissionLevel(value)
    except ValueError as exc:
        raise PermissionPolicyError("permission_denied", "未知权限档位") from exc


def _parse_mode(value: TaskMode | str) -> TaskMode:
    try:
        return TaskMode(value)
    except ValueError as exc:
        raise PermissionPolicyError("permission_denied", "未知运行模式") from exc


def _parse_provider(value: Provider | str) -> Provider:
    try:
        return Provider(value)
    except ValueError as exc:
        raise PermissionPolicyError(
            "unsupported_capability", "未知 Coding Agent Provider"
        ) from exc
