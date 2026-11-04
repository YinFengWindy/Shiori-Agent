"""MCP launch credential detection and JSON-preserving output redaction."""

from __future__ import annotations

import json
import re
from typing import Any

from shiori_sdk.redaction import redact_secrets
from .models import LaunchCredentials

_HIDDEN = "[已隐藏]"


def _credential_name(name: str) -> bool:
    # Use the SDK's public redactor as the authority for credential vocabulary.
    # Normalize CLI/camelCase spellings and allow namespaced env keys such as
    # SERVICE_API_KEY without treating ordinary DEBUG/FORMAT options as secrets.
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).strip("-")
    parts = re.split(r"[-_ ]+", normalized.lower())
    for index in range(len(parts)):
        probe = "_".join(parts[index:]) + "=credential_name_probe"
        if redact_secrets(probe) != probe:
            return True
    return False


def _credential_values(launch: LaunchCredentials) -> tuple[str, ...]:
    values = {
        value for name, value in launch.env.items() if _credential_name(name) and value
    }
    arguments = launch.command[1:]
    for index, argument in enumerate(arguments):
        name, separator, value = argument.partition("=")
        if separator and _credential_name(name):
            values.add(value)
        elif (
            argument.startswith("-")
            and _credential_name(argument)
            and index + 1 < len(arguments)
        ):
            values.add(arguments[index + 1])
    # Authorization headers may be echoed without their Bearer/Basic scheme.
    for value in tuple(values):
        if match := re.fullmatch(r"(?i)(?:bearer|basic)\s+(\S+)", value):
            values.add(match[1])
    values.discard("")
    return tuple(sorted(values, key=len, reverse=True))


class LaunchRedactor:
    """Snapshot the credentials used by a call, even if settings change meanwhile."""

    def __init__(self, launch: LaunchCredentials):
        self._values = _credential_values(launch)

    def _plain(self, text: str) -> str:
        for value in self._values:
            text = text.replace(value, _HIDDEN)
        return redact_secrets(text)

    def text(self, text: str) -> str:
        """Redact JSON by value so substitutions never break its wire syntax."""
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return self._plain(text)
        scrubbed = self.data(data)
        return text if scrubbed == data else json.dumps(scrubbed, ensure_ascii=False)

    def data(self, value: Any) -> Any:
        """Preserve schemas, numbers and media; redact known secrets in text leaves."""
        if isinstance(value, str):
            return self._plain(value)
        if isinstance(value, list):
            return [self.data(item) for item in value]
        if isinstance(value, dict):
            return {
                self._plain(key): (
                    _HIDDEN
                    if isinstance(item, str) and item and _credential_name(key)
                    else self.data(item)
                )
                for key, item in value.items()
            }
        return value
