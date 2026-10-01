from __future__ import annotations

import re
from urllib.parse import urlsplit

from agent.config_models import ModelRegistration


class ModelConfigurationError(ValueError):
    """A model-dependent operation cannot run until its configuration is repaired."""

    code = "model_configuration_required"

    def __init__(
        self,
        *,
        reason: str,
        role_id: str = "",
        purpose: str = "chat",
        registration_id: str = "",
        fields: tuple[str, ...] = (),
    ) -> None:
        self.reason = reason
        self.role_id = role_id
        self.purpose = purpose
        self.registration_id = registration_id
        self.fields = fields
        messages = {
            "no_models": "尚未配置模型，请先在设置中添加模型",
            "role_unbound": "角色未选择对话模型，请先绑定模型",
            "registration_missing": "原先选择的模型已不存在，请重新选择模型",
            "connection_incomplete": "模型配置需补填，请检查连接和上下文容量",
        }
        super().__init__(messages[reason])

    def to_details(self):
        """Returns non-secret structured context for RPC errors and availability."""
        return {
            "code": self.code,
            "reason": self.reason,
            "role_id": self.role_id,
            "purpose": self.purpose,
            "registration_id": self.registration_id,
            "fields": list(self.fields),
        }


def incomplete_registration_fields(registration: ModelRegistration):
    """Check all fields needed for a budgeted conversation, without network access."""
    capacity_fields = tuple(
        name
        for name in ("context_window_tokens", "max_output_tokens")
        if getattr(registration, name) is None
    )
    return incomplete_connection_fields(registration) + capacity_fields


def incomplete_connection_fields(registration: ModelRegistration):
    """Check endpoint reachability configuration independently of model capacity."""
    fields = []
    for name in ("provider", "model"):
        if not getattr(registration, name).strip():
            fields.append(name)
    base_url = registration.base_url.strip()
    try:
        parsed = urlsplit(base_url)
        local_endpoint = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        invalid_url = bool(base_url) and (
            parsed.scheme not in {"http", "https"} or not parsed.netloc
        )
    except ValueError:
        local_endpoint = False
        invalid_url = True
    api_key = registration.api_key.strip()
    if re.search(r"\$\{\w+\}", api_key) or (not api_key and not local_endpoint):
        fields.append("api_key")
    if invalid_url:
        fields.append("base_url")
    return tuple(fields)
