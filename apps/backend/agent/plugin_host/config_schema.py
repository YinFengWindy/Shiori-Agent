"""Manifest configuration models, schema export, and validated plugin values."""

from __future__ import annotations

import importlib
import sys
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from agent.plugin_host.handle import PluginRecord


class ConfigModelError(Exception):
    """``config_model`` 声明非法，或未指向 pydantic BaseModel 子类。"""


def format_validation_error(error: ValidationError) -> str:
    """Renders a pydantic validation error as one readable ``path: msg`` line."""

    parts: list[str] = []
    for item in error.errors():
        path = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
        parts.append(f"{path}: {item.get('msg', 'invalid')}")
    return "; ".join(parts)


def validate_against(
    model_cls: type[BaseModel], values: dict[str, Any]
) -> dict[str, Any]:
    """Validates and normalizes values against a config model.

    直接接收模型类，供需要跨 generation 边界持有模型的调用方使用。
    """

    return model_cls.model_validate(values).model_dump(mode="json")


def resolve_config_model(record: PluginRecord) -> type[BaseModel] | None:
    """Returns the plugin's declared config model class, or None when undeclared."""

    if record.manifest.config_model:
        return _resolve_manifest_config_model(record)
    return None


def _resolve_manifest_config_model(record: PluginRecord) -> type[BaseModel]:
    spec = str(record.manifest.config_model)
    module_suffix, sep, class_name = spec.partition(":")
    if sep:
        module_name = f"{record.import_path}.{module_suffix}"
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise ConfigModelError(
                f"插件 {record.name} 的 config_model 模块导入失败 ({module_name}): {e}"
            ) from e
    else:
        class_name = module_suffix
        module = sys.modules.get(record.import_path)
        if module is None:
            raise ConfigModelError(
                f"插件 {record.name} 的入口模块尚未导入，无法解析 config_model"
            )
    model_cls = getattr(module, class_name, None)
    if not (isinstance(model_cls, type) and issubclass(model_cls, BaseModel)):
        raise ConfigModelError(
            f"插件 {record.name} 的 config_model={spec!r} 未指向 pydantic BaseModel 子类"
        )
    return model_cls


class PluginConfigSchemaRegistry:
    """内核持有的 plugin_id -> config 模型映射；供 plugin.config.* 通道查询。"""

    def __init__(self) -> None:
        self._models: dict[str, type[BaseModel]] = {}

    def register(self, plugin_id: str, model_cls: type[BaseModel]) -> None:
        self._models[plugin_id] = model_cls

    def unregister(self, plugin_id: str) -> None:
        self._models.pop(plugin_id, None)

    def schema_for(self, plugin_id: str) -> dict[str, Any] | None:
        """Returns the JSON Schema for a plugin's config model, or None."""
        model_cls = self._models.get(plugin_id)
        return model_cls.model_json_schema() if model_cls is not None else None

    def defaults_for(self, plugin_id: str) -> dict[str, Any] | None:
        """Returns default values for fields that declare one, or None with no model.

        Reads defaults straight off ``model_fields`` instead of instantiating
        the model: constructing an instance fails for the whole model as soon
        as a single required field has no default, which would blank out
        every other field's default along with it. A field without a default
        (required) is simply absent from the result.

        The values are converted to their JSON form, matching ``validate_against``:
        this result is merged with stored values and serialised straight onto
        the bridge, so a default that is an ``Enum`` / ``datetime`` / ``Path``
        / nested model must not reach the transport as a raw Python object.
        """
        model_cls = self._models.get(plugin_id)
        if model_cls is None:
            return None
        return {
            name: to_jsonable_python(field_info.get_default(call_default_factory=True))
            for name, field_info in model_cls.model_fields.items()
            if not field_info.is_required()
        }

    def model_for(self, plugin_id: str) -> type[BaseModel] | None:
        """Returns the plugin's registered config model, or None.

        写入路径应当在开始时取出模型类并一路持有它，而不是反复回查注册表：
        注册表随 generation 生灭，一次配置写入跨越了事务锁的等待，期间旧代可能
        已被处置、schema 随之注销，再查就会抛 KeyError。模型类本身是不可变的，
        与 generation 无关。
        """
        return self._models.get(plugin_id)
