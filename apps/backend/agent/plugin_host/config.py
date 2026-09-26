from __future__ import annotations

from typing import Any


class PluginConfig:
    """Snapshot of the plugin values granted by the host configuration."""

    def __init__(
        self, values: dict[str, Any], *, raw_values: dict[str, Any] | None = None
    ) -> None:
        self._values = dict(values)
        self._raw_values = dict(raw_values) if raw_values is not None else dict(values)

    def get(self, key: str, default: Any = None) -> Any:
        """Reads a configured value with an optional default."""
        return self._values.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        """Returns a copy for validation by the plugin configuration model."""
        return dict(self._values)

    def raw_as_dict(self) -> dict[str, Any]:
        """Returns unexpanded plugin values for reference-preserving migrations."""
        return dict(self._raw_values)

    def __getattr__(self, key: str) -> Any:
        try:
            return self._values[key]
        except KeyError as e:
            raise AttributeError(key) from e
