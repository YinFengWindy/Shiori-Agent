"""Feishu/Lark applications saved in the plugin's own storage, never in host config."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, field_validator

from agent.config import resolve_config_references

from .formatting import DOMAINS, FEISHU_DOMAIN, LARK_DOMAIN

if TYPE_CHECKING:
    from agent.plugin_host.kv import PluginKVStore

UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")
_DOMAIN_ALIASES = {FEISHU_DOMAIN: "feishu", LARK_DOMAIN: "lark"}
# KV key of the saved application list.
APPLICATIONS_KEY = "applications"
# Per-application KV caches written by the channel and the profile RPC.
_CACHE_PREFIXES = ("profile", "targets", "contacts")


class FeishuAppConfig(BaseModel):
    """One custom bot application and its regional credential.

    ``app_secret`` is a literal secret or a whole ``${NAME}`` reference, kept
    verbatim and resolved only when connecting or verifying.
    """

    app_id: str
    app_secret: str = ""
    domain: Literal["feishu", "lark"] = "feishu"

    @field_validator("app_id", mode="before")
    @classmethod
    def _normalize_app_id(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text or ":" in text or "${" in text:
            raise ValueError("飞书 App ID 无效")
        return text

    @field_validator("app_secret", mode="before")
    @classmethod
    def _normalize_secret(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("domain", mode="before")
    @classmethod
    def _normalize_domain(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip().rstrip("/")
            return _DOMAIN_ALIASES.get(text, text.lower() or "feishu")
        return value

    @property
    def ref(self) -> str:
        """Stable regional reference: config_ref, platform account and channel suffix."""
        return f"{self.domain}:{self.app_id}"

    @property
    def base_url(self) -> str:
        """Regional OpenAPI endpoint."""
        return DOMAINS[self.domain]

    def resolved_secret(self) -> str:
        """The usable secret; empty when missing or its ``${NAME}`` is unset."""
        secret = str(resolve_config_references(self.app_secret)).strip()
        return "" if UNRESOLVED_ENV_RE.fullmatch(secret) else secret


class FeishuApplication(FeishuAppConfig):
    """A saved application: credential, owner role, connection intent, rules."""

    connection_enabled: bool = True
    role_id: str = ""
    # ``core.accounts.response_rules_to_dict`` JSON; None until first edited.
    response_rules: dict[str, Any] | None = None


class FeishuApplicationStore:
    """The ``applications`` list in the plugin KV store, keyed by ``ref``."""

    def __init__(self, kv: PluginKVStore) -> None:
        self._kv = kv

    def rows(self) -> list[Any]:
        """Raw saved entries; each is parsed on its own so one bad entry is isolated."""
        rows = self._kv.get(APPLICATIONS_KEY, [])
        if not isinstance(rows, list):
            raise ValueError("飞书应用数据格式错误")
        return rows

    def get(self, ref: str) -> FeishuApplication | None:
        """The saved application behind ``ref``, if any."""
        for row in self.rows():
            try:
                app = FeishuApplication.model_validate(row)
            except ValueError:
                continue
            if app.ref == ref:
                return app
        return None

    def save(self, app: FeishuApplication) -> None:
        """Adds or replaces one application's entry."""
        kept = [row for row in self.rows() if _row_ref(row) != app.ref]
        self._kv.set(
            APPLICATIONS_KEY, [*kept, app.model_dump(mode="json", exclude_none=True)]
        )

    def remove(self, ref: str) -> None:
        """Deletes the application's entry and caches; idempotent."""
        rows = self.rows()
        kept = [row for row in rows if _row_ref(row) != ref]
        if len(kept) != len(rows):
            self._kv.set(APPLICATIONS_KEY, kept)
        for prefix in _CACHE_PREFIXES:
            self._kv.delete(f"{prefix}:{ref}")


def _row_ref(row: Any) -> str:
    try:
        return FeishuAppConfig.model_validate(row).ref
    except ValueError:
        return ""
