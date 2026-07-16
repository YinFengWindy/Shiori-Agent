from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from coding_agents.models import PermissionLevel, Provider


class ProfileError(ValueError):
    """命名模型 Profile 配置或选择失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProfileEffort(StrEnum):
    """命名 Profile 可声明的推理强度。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


@dataclass(frozen=True)
class ModelProfile:
    """服务端白名单中的命名模型配置。"""

    profile_id: str
    provider: Provider
    model: str
    effort: ProfileEffort
    timeout_seconds: int
    max_budget_usd: Decimal | None = None
    max_permission_level: PermissionLevel = PermissionLevel.WORKSPACE_WRITE
    max_parallel_runs: int | None = None


@dataclass(frozen=True)
class ProfileSnapshot:
    """Run 启动时固化的 Profile 与权限快照。"""

    profile_id: str
    provider: Provider
    model: str
    effort: ProfileEffort
    timeout_seconds: int
    max_budget_usd: Decimal | None
    permission_level: PermissionLevel
    cli_version: str


class ProfileRegistry:
    """严格加载、选择并固化命名模型 Profile。"""

    def __init__(
        self,
        profiles: Iterable[ModelProfile],
        *,
        default_profile_id: str | None = None,
    ) -> None:
        self._profiles: dict[str, ModelProfile] = {}
        for profile in profiles:
            validated = validate_profile(profile)
            if validated.profile_id in self._profiles:
                raise ProfileError("profile_invalid", "Profile ID 重复")
            self._profiles[validated.profile_id] = validated
        if default_profile_id is not None and default_profile_id not in self._profiles:
            raise ProfileError("profile_not_found", "默认 Profile 不存在")
        self.default_profile_id = default_profile_id

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Mapping[str, Any]],
        *,
        default_profile_id: str | None = None,
    ) -> ProfileRegistry:
        """从 TOML 解码后的映射构建严格 Profile 注册表。"""
        return cls(
            (_profile_from_mapping(profile_id, data) for profile_id, data in payload.items()),
            default_profile_id=default_profile_id,
        )

    def list(self) -> tuple[ModelProfile, ...]:
        """按 Profile ID 稳定列出所有白名单配置。"""
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def get(self, profile_id: str) -> ModelProfile:
        """读取一个显式 Profile，不对缺失项静默回退。"""
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise ProfileError("profile_not_found", f"Profile 不存在：{profile_id}") from exc

    def select(
        self,
        *,
        explicit_profile_id: str | None = None,
        skill_profile_id: str | None = None,
    ) -> ModelProfile:
        """按用户显式、Skill 推荐、全局默认的顺序选择 Profile。"""
        selected_id = explicit_profile_id or skill_profile_id or self.default_profile_id
        if not selected_id:
            raise ProfileError("profile_not_found", "没有可用的默认 Profile")
        return self.get(selected_id)

    def snapshot(
        self,
        profile_id: str,
        *,
        permission_level: PermissionLevel | str,
        cli_version: str,
    ) -> ProfileSnapshot:
        """校验权限上限并创建不会随配置变化的 Run 快照。"""
        profile = self.get(profile_id)
        try:
            permission = PermissionLevel(permission_level)
        except ValueError as exc:
            raise ProfileError("permission_denied", "未知权限档位") from exc
        if _permission_rank(permission) > _permission_rank(profile.max_permission_level):
            raise ProfileError("permission_denied", "请求权限超过 Profile 上限")
        version = cli_version.strip()
        if not version:
            raise ProfileError("provider_unavailable", "CLI 版本不能为空")
        return ProfileSnapshot(
            profile_id=profile.profile_id,
            provider=profile.provider,
            model=profile.model,
            effort=profile.effort,
            timeout_seconds=profile.timeout_seconds,
            max_budget_usd=profile.max_budget_usd,
            permission_level=permission,
            cli_version=version,
        )


def validate_profile(profile: ModelProfile) -> ModelProfile:
    """验证一个命名 Profile 的 Provider 专属字段和运行上限。"""
    profile_id = profile.profile_id.strip()
    model = profile.model.strip()
    if not profile_id or not model:
        raise ProfileError("profile_invalid", "Profile ID 和 model 不能为空")
    if profile.timeout_seconds <= 0:
        raise ProfileError("profile_invalid", "timeout_seconds 必须大于零")
    if profile.max_parallel_runs is not None and profile.max_parallel_runs <= 0:
        raise ProfileError("profile_invalid", "max_parallel_runs 必须大于零")
    try:
        provider = Provider(profile.provider)
        effort = ProfileEffort(profile.effort)
        max_permission_level = PermissionLevel(profile.max_permission_level)
    except ValueError as exc:
        raise ProfileError("profile_invalid", "Profile 枚举字段无效") from exc
    allowed_efforts = {
        Provider.CODEX: {
            ProfileEffort.LOW,
            ProfileEffort.MEDIUM,
            ProfileEffort.HIGH,
            ProfileEffort.XHIGH,
        },
        Provider.CLAUDE: {
            ProfileEffort.LOW,
            ProfileEffort.MEDIUM,
            ProfileEffort.HIGH,
            ProfileEffort.MAX,
        },
    }
    if effort not in allowed_efforts[provider]:
        raise ProfileError(
            "profile_invalid", f"{provider.value} 不支持 effort={effort.value}"
        )
    if provider is Provider.CODEX and profile.max_budget_usd is not None:
        raise ProfileError("profile_invalid", "Codex Profile 不支持 max_budget_usd")
    if profile.max_budget_usd is not None and profile.max_budget_usd <= 0:
        raise ProfileError("profile_invalid", "max_budget_usd 必须大于零")
    return ModelProfile(
        profile_id=profile_id,
        provider=provider,
        model=model,
        effort=effort,
        timeout_seconds=profile.timeout_seconds,
        max_budget_usd=profile.max_budget_usd,
        max_permission_level=max_permission_level,
        max_parallel_runs=profile.max_parallel_runs,
    )


def _profile_from_mapping(profile_id: str, data: Mapping[str, Any]) -> ModelProfile:
    allowed_fields = {
        "provider",
        "model",
        "effort",
        "timeout_seconds",
        "max_budget_usd",
        "max_permission_level",
        "max_parallel_runs",
        "command",
    }
    unknown = set(data) - allowed_fields
    if unknown:
        raise ProfileError(
            "profile_invalid", f"Profile 包含未知字段：{', '.join(sorted(unknown))}"
        )
    try:
        provider = Provider(str(data["provider"]))
        effort = ProfileEffort(str(data["effort"]))
        timeout_seconds = _strict_int(data["timeout_seconds"], "timeout_seconds")
        permission = PermissionLevel(
            str(
                data.get(
                    "max_permission_level",
                    PermissionLevel.WORKSPACE_WRITE.value,
                )
            )
        )
    except KeyError as exc:
        raise ProfileError("profile_invalid", f"Profile 缺少字段：{exc.args[0]}") from exc
    except ValueError as exc:
        raise ProfileError("profile_invalid", "Profile 枚举字段无效") from exc
    budget = _optional_decimal(data.get("max_budget_usd"))
    command = str(data.get("command") or provider.value).strip()
    if command != provider.value:
        raise ProfileError(
            "profile_invalid",
            "Profile command 只能等于 provider，不能覆盖任意 CLI 命令",
        )
    max_parallel = data.get("max_parallel_runs")
    if max_parallel is not None:
        max_parallel = _strict_int(max_parallel, "max_parallel_runs")
    return validate_profile(
        ModelProfile(
            profile_id=profile_id,
            provider=provider,
            model=str(data.get("model", "")),
            effort=effort,
            timeout_seconds=timeout_seconds,
            max_budget_usd=budget,
            max_permission_level=permission,
            max_parallel_runs=max_parallel,
        )
    )


def _strict_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileError("profile_invalid", f"{field_name} 必须是整数")
    return value


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProfileError("profile_invalid", "max_budget_usd 格式无效") from exc
    if not result.is_finite():
        raise ProfileError("profile_invalid", "max_budget_usd 格式无效")
    return result


def _permission_rank(level: PermissionLevel) -> int:
    return {
        PermissionLevel.READ_ONLY: 0,
        PermissionLevel.WORKSPACE_WRITE: 1,
        PermissionLevel.FULL_ACCESS: 2,
    }[level]
