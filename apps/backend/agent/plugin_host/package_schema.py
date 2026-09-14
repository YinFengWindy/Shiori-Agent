"""Strict manifest field readers shared by backend and renderer contracts."""

from typing import Any

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.versions import satisfies


def string_field(value: object, field: str) -> str:
    """Read a nonempty string without YAML scalar coercion."""
    if not isinstance(value, str) or not value.strip():
        raise PackageContractError(
            "invalid_manifest", field, "Expected a nonempty string"
        )
    return value


def string_list(value: object, field: str) -> tuple[str, ...]:
    """Read a list and report the index of malformed values."""
    if not isinstance(value, list):
        raise PackageContractError(
            "invalid_manifest", field, "Expected a list of strings"
        )
    items: list[object] = value
    return tuple(
        string_field(item, f"{field}[{index}]") for index, item in enumerate(items)
    )


def object_field(
    value: object, field: str, allowed: set[str] | None = None
) -> dict[str, Any]:
    """Read a mapping, optionally rejecting unknown schema fields."""
    if not isinstance(value, dict):
        raise PackageContractError("invalid_manifest", field, "Expected an object")
    mapping: dict[Any, Any] = value
    if any(not isinstance(key, str) for key in mapping):
        raise PackageContractError("invalid_manifest", field, "Expected an object")
    if allowed is not None and (unknown := set(mapping) - allowed):
        raise PackageContractError(
            "invalid_manifest", field, f"Unknown fields: {sorted(unknown)}"
        )
    return mapping


def compatible_range(version: str, value: object, field: str) -> str:
    """Require the advertised host version to match a supported range."""
    expression = string_field(value, field)
    try:
        compatible = satisfies(version, expression)
    except ValueError as exc:
        raise PackageContractError("invalid_version_range", field, str(exc)) from exc
    if not compatible:
        raise PackageContractError(
            "incompatible_runtime",
            field,
            f"Host {version} does not satisfy {expression}",
        )
    return expression
