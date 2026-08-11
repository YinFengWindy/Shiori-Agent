from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*$")
_CONFIG_PATH_PATTERN = re.compile(r"^[a-z][A-Za-z0-9]*(?:\.[a-z][A-Za-z0-9]*)+$")
_SUPPORTED_SCHEMA_VERSION = 1
_SUPPORTED_SETTING_TYPES = {"boolean", "number", "secret", "select", "string"}


class PluginManifestError(ValueError):
    """Raised when a plugin manifest cannot form a stable public contract."""


@dataclass(frozen=True)
class PluginSettingOption:
    """One renderer-safe option for a declarative select field."""

    label: str
    value: str | int | float

    def to_public_dict(self) -> dict[str, str | int | float]:
        return {"label": self.label, "value": self.value}


@dataclass(frozen=True)
class PluginSettingField:
    """One declarative settings field bound to the shared settings draft."""

    id: str
    label: str
    field_type: str
    config_path: str
    hint: str = ""
    options: tuple[PluginSettingOption, ...] = ()

    def to_public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "label": self.label,
            "type": self.field_type,
            "config_path": self.config_path,
        }
        if self.hint:
            result["hint"] = self.hint
        if self.options:
            result["options"] = [option.to_public_dict() for option in self.options]
        return result


@dataclass(frozen=True)
class PluginUiContribution:
    """One renderer contribution mounted into a fixed PluginHost slot."""

    id: str
    slot: str
    title: str
    renderer: str
    order: int = 0
    settings_schema: tuple[PluginSettingField, ...] = ()

    def to_public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "slot": self.slot,
            "title": self.title,
            "renderer": self.renderer,
            "order": self.order,
        }
        if self.settings_schema:
            result["settings_schema"] = [
                field.to_public_dict() for field in self.settings_schema
            ]
        return result


@dataclass(frozen=True)
class PluginManifest:
    """Validated plugin identity, permissions, and renderer contributions."""

    schema_version: int
    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    capabilities: tuple[str, ...]
    rpc_methods: tuple[str, ...]
    ui_contributions: tuple[PluginUiContribution, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "capabilities": list(self.capabilities),
            "rpc_methods": list(self.rpc_methods),
            "ui_contributions": [
                contribution.to_public_dict() for contribution in self.ui_contributions
            ],
        }


def load_plugin_manifest(
    plugin_dir: Path,
    *,
    fallback_id: str,
    instance: object,
) -> PluginManifest:
    """Loads and validates one manifest while preserving legacy class metadata."""

    raw = _read_manifest(plugin_dir / "manifest.yaml")
    schema_version = _as_int(raw.get("schema_version"), default=1)
    if schema_version != _SUPPORTED_SCHEMA_VERSION:
        raise PluginManifestError(
            f"unsupported manifest schema_version: {schema_version}"
        )
    plugin_id = str(
        raw.get("plugin_id")
        or raw.get("name")
        or getattr(instance, "name", None)
        or fallback_id
    ).strip()
    if not _PLUGIN_ID_PATTERN.fullmatch(plugin_id):
        raise PluginManifestError(f"invalid plugin_id: {plugin_id!r}")

    name = str(raw.get("display_name") or raw.get("name") or plugin_id).strip()
    version = str(
        raw.get("version") or getattr(instance, "version", None) or ""
    ).strip()
    description = str(
        raw.get("description")
        or raw.get("desc")
        or getattr(instance, "desc", None)
        or ""
    ).strip()
    author = str(raw.get("author") or getattr(instance, "author", None) or "").strip()
    capabilities = _string_tuple(raw.get("capabilities"), field="capabilities")
    rpc = raw.get("rpc")
    rpc_methods = _string_tuple(
        cast(dict[str, Any], rpc).get("methods") if isinstance(rpc, dict) else None,
        field="rpc.methods",
    )
    ui = raw.get("ui")
    ui_raw = (
        cast(dict[str, Any], ui).get("contributions") if isinstance(ui, dict) else None
    )
    contributions = _parse_ui_contributions(ui_raw)
    _validate_rpc_namespace(plugin_id, rpc_methods)
    _apply_legacy_metadata(instance, name, version, description, author)
    return PluginManifest(
        schema_version=schema_version,
        plugin_id=plugin_id,
        name=name,
        version=version,
        description=description,
        author=author,
        capabilities=capabilities,
        rpc_methods=rpc_methods,
        ui_contributions=contributions,
    )


def peek_plugin_id(plugin_dir: Path, fallback_id: str) -> str:
    """Returns a discoverable plugin ID without importing plugin code."""

    raw = _read_manifest(plugin_dir / "manifest.yaml")
    plugin_id = str(raw.get("plugin_id") or raw.get("name") or fallback_id).strip()
    return plugin_id if _PLUGIN_ID_PATTERN.fullmatch(plugin_id) else fallback_id


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PluginManifestError(f"failed to read {path.name}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise PluginManifestError(f"{path.name} must contain an object")
    return cast(dict[str, Any], loaded)


def _parse_ui_contributions(value: object) -> tuple[PluginUiContribution, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PluginManifestError("ui.contributions must be a list")
    contributions: list[PluginUiContribution] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            raise PluginManifestError("each UI contribution must be an object")
        item = cast(dict[str, Any], raw_item)
        contribution_id = str(item.get("id") or "").strip()
        slot = str(item.get("slot") or "").strip()
        renderer = str(item.get("renderer") or "").strip()
        title = str(item.get("title") or contribution_id).strip()
        if not contribution_id or not slot or not renderer:
            raise PluginManifestError("UI contributions require id, slot, and renderer")
        if contribution_id in seen:
            raise PluginManifestError(
                f"duplicate UI contribution id: {contribution_id}"
            )
        seen.add(contribution_id)
        contributions.append(
            PluginUiContribution(
                id=contribution_id,
                slot=slot,
                title=title,
                renderer=renderer,
                order=_as_int(item.get("order"), default=0),
                settings_schema=_parse_settings_schema(item.get("schema")),
            )
        )
        contribution = contributions[-1]
        if contribution.settings_schema and (
            contribution.slot != "settings"
            or contribution.renderer != "schema.settings"
        ):
            raise PluginManifestError(
                "declarative settings schema requires the settings slot "
                "and schema.settings renderer"
            )
        if (
            contribution.renderer == "schema.settings"
            and not contribution.settings_schema
        ):
            raise PluginManifestError("schema.settings requires a non-empty schema")
    return tuple(sorted(contributions, key=lambda item: (item.order, item.id)))


def _parse_settings_schema(value: object) -> tuple[PluginSettingField, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PluginManifestError("UI contribution schema must be a list")
    fields: list[PluginSettingField] = []
    seen: set[str] = set()
    for raw_field in value:
        if not isinstance(raw_field, dict):
            raise PluginManifestError("each settings schema field must be an object")
        field = cast(dict[str, Any], raw_field)
        field_id = str(field.get("id") or "").strip()
        label = str(field.get("label") or field_id).strip()
        field_type = str(field.get("type") or "string").strip()
        config_path = str(field.get("config_path") or "").strip()
        if not field_id or not label or not config_path:
            raise PluginManifestError(
                "settings schema fields require id, label, and config_path"
            )
        if field_id in seen:
            raise PluginManifestError(f"duplicate settings schema field id: {field_id}")
        if field_type not in _SUPPORTED_SETTING_TYPES:
            raise PluginManifestError(
                f"unsupported settings schema field type: {field_type}"
            )
        if not _CONFIG_PATH_PATTERN.fullmatch(config_path):
            raise PluginManifestError(f"invalid settings config_path: {config_path!r}")
        options = _parse_setting_options(field.get("options"))
        if field_type == "select" and not options:
            raise PluginManifestError("select settings fields require options")
        if field_type != "select" and options:
            raise PluginManifestError("only select settings fields may declare options")
        seen.add(field_id)
        fields.append(
            PluginSettingField(
                id=field_id,
                label=label,
                field_type=field_type,
                config_path=config_path,
                hint=str(field.get("hint") or "").strip(),
                options=options,
            )
        )
    return tuple(fields)


def _parse_setting_options(value: object) -> tuple[PluginSettingOption, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PluginManifestError("settings field options must be a list")
    options: list[PluginSettingOption] = []
    for raw_option in value:
        if not isinstance(raw_option, dict):
            raise PluginManifestError("each settings field option must be an object")
        option = cast(dict[str, Any], raw_option)
        label = str(option.get("label") or "").strip()
        option_value = option.get("value")
        if (
            not label
            or isinstance(option_value, bool)
            or not isinstance(option_value, (str, int, float))
        ):
            raise PluginManifestError(
                "settings field options require a label and string or numeric value"
            )
        options.append(PluginSettingOption(label=label, value=option_value))
    return tuple(options)


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PluginManifestError(f"{field} must be a list")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if len(result) != len(set(result)):
        raise PluginManifestError(f"{field} contains duplicate values")
    return result


def _validate_rpc_namespace(plugin_id: str, methods: tuple[str, ...]) -> None:
    prefix = f"{plugin_id}."
    invalid = [method for method in methods if not method.startswith(prefix)]
    if invalid:
        raise PluginManifestError(
            f"RPC methods must use the {prefix} namespace: {invalid[0]}"
        )


def _as_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise PluginManifestError("boolean values are not valid integers")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PluginManifestError(f"invalid integer value: {value!r}") from exc


def _apply_legacy_metadata(
    instance: object,
    name: str,
    version: str,
    description: str,
    author: str,
) -> None:
    setattr(instance, "name", name)
    setattr(instance, "version", version)
    setattr(instance, "desc", description)
    setattr(instance, "author", author)
