"""Plugin-owned role settings; persistence remains in the original role JSON."""

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from shiori_sdk.roles import Roles

from .service import role_proactive_config


class RoleSettingsPatch(BaseModel):
    """Only edited panel values, validated before changing persisted state."""

    model_config = ConfigDict(extra="forbid")
    proactiveEnabled: StrictBool = False
    proactiveProfile: Literal["daily", "quiet", "dev_verify"] = "daily"
    proactiveAgentMaxSteps: int = Field(default=35, strict=True, ge=1)
    proactiveAgentContentLimit: int = Field(default=5, strict=True, ge=1)
    proactiveAgentWebFetchMaxChars: int = Field(default=8000, strict=True, ge=1)
    proactiveDriftMaxSteps: int = Field(default=20, strict=True, ge=1)
    proactiveDriftMinIntervalHours: float = Field(default=3, ge=0, allow_inf_nan=False)


def _section(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("主动设置参数必须是对象")
    return dict(value)


class ProactiveRoleSettings:
    """Read projections and apply sparse patches through ROLES.plugin_settings."""

    def __init__(self, roles: Roles):
        self._roles = roles

    def project(self, role_id: str, _data: dict[str, object]) -> dict[str, object]:
        """Expose editable values only while the plugin is active."""
        stored = self._roles.plugin_settings(role_id, "proactive").read()
        agent = _section(stored.get("agent"))
        drift = _section(stored.get("drift"))
        return {
            "proactiveEnabled": bool(stored.get("enabled", False)),
            "proactiveProfile": stored.get("profile") or "daily",
            "proactiveAgentMaxSteps": agent.get("max_steps", 35),
            "proactiveAgentContentLimit": agent.get("content_limit", 5),
            "proactiveAgentWebFetchMaxChars": agent.get("web_fetch_max_chars", 8000),
            "proactiveDriftMaxSteps": drift.get("max_steps", 20),
            "proactiveDriftMinIntervalHours": drift.get("min_interval_hours", 3),
        }

    def reject_draft(
        self, _role_id: str, _values: dict[str, object], _data: dict[str, object]
    ) -> None:
        """The opaque legacy namespace is saved by this plugin's RPC only."""
        raise ValueError("主动设置请通过主动推送插件保存")

    async def set(self, payload: dict[str, object]) -> dict[str, object]:
        """Merge edited fields over the latest data without restoring retired keys."""
        role_id = str(payload.get("role_id") or "")
        patch = RoleSettingsPatch.model_validate(payload.get("values")).model_dump(
            exclude_unset=True
        )
        with self._roles.read_scope():
            storage = self._roles.plugin_settings(role_id, "proactive")
            stored = deepcopy(dict(storage.read()))
            stored.setdefault(
                "policy_configured",
                any(
                    key in stored for key in ("profile", "overrides", "agent", "drift")
                ),
            )
            stored.setdefault("enabled", False)
            stored.setdefault("profile", "daily")
            stored.setdefault("overrides", {})
            agent = _section(stored.get("agent"))
            drift = _section(stored.get("drift"))
            agent.pop("model", None)
            drift.pop("enabled", None)
            for key, destination, name in (
                ("proactiveEnabled", stored, "enabled"),
                ("proactiveProfile", stored, "profile"),
                ("proactiveAgentMaxSteps", agent, "max_steps"),
                ("proactiveAgentContentLimit", agent, "content_limit"),
                ("proactiveAgentWebFetchMaxChars", agent, "web_fetch_max_chars"),
                ("proactiveDriftMaxSteps", drift, "max_steps"),
                ("proactiveDriftMinIntervalHours", drift, "min_interval_hours"),
            ):
                if key in patch:
                    destination[name] = patch[key]
            stored.update(agent=agent, drift=drift, candidates=[])
            role_proactive_config(role_id, stored)
            storage.write(stored)
            return self.project(role_id, {})
