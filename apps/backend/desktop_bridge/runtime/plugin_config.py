"""Plugin config schema channel: validate, merge into TOML, and hot-apply.

Owns the ``plugin.config.get``/``plugin.config.set`` request bodies so
``ReloadableDesktopService`` only has to dispatch to it, not implement
validation, TOML merging and the round-trip guard itself.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from agent.config import has_config_reference, resolve_config_references
from agent.plugin_host.config_schema import (
    format_validation_error,
    validate_against,
)
from agent.plugin_host.kernel import PLUGIN_ENABLED_CONFIG_KEY, PluginKernel
from bootstrap.app import AppRuntime
from desktop_bridge.plugin_config_text import PluginTableConflict, merge_plugin_table
from desktop_bridge.runtime.apply import (
    DerivedWrite,
    RuntimeApplyError,
    RuntimeSettingsApplication,
    assert_plugin_table_isolated,
    read_plugin_table,
)


class RuntimePluginConfig:
    """Reads and writes one plugin's ``[plugins.<id>]`` table via its config schema."""

    def __init__(self, app: AppRuntime, settings: RuntimeSettingsApplication) -> None:
        self._app = app
        self._settings = settings

    def get(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Returns a plugin's declared JSON Schema (or None) and current values.

        Values come from the committed config text, *not* the runtime's
        ``AppRuntime.config``: the latter has every ``${NAME}`` reference
        already expanded, and the renderer round-trips the whole table on save,
        so handing it resolved values would both leak the secret to the UI and
        write it back to config.toml as plaintext on the next unrelated edit.
        ``env_status`` tells the UI, per top-level field holding a reference,
        whether that reference currently resolves.
        """
        plugin_id = str(payload.get("plugin_id") or "").strip()
        if not plugin_id:
            raise RuntimeApplyError("runtime_invalid_request", "plugin_id 不能为空")
        kernel = self._plugin_kernel()
        schema = (
            kernel.config_schemas.schema_for(plugin_id) if kernel is not None else None
        )
        stored = read_plugin_table(self._settings.config_text, plugin_id)
        # 启停状态归宿主所有，由 plugins.list / plugins.setEnabled 管理；
        # 不要混进配置表单的值里被 renderer 原样回传。
        _ = stored.pop(PLUGIN_ENABLED_CONFIG_KEY, None)
        if schema is None:
            values = stored
        else:
            defaults = kernel.config_schemas.defaults_for(plugin_id) or {}
            values = {**defaults, **stored}
        return {
            "plugin_id": plugin_id,
            "schema": schema,
            "values": values,
            "env_status": _env_status(values),
        }

    async def set(
        self,
        payload: dict[str, Any],
        *,
        prepare_service: Callable,
        publish_service: Callable,
    ) -> dict[str, Any]:
        """Validates, commits and hot-applies one plugin's ``[plugins.<id>]`` table.

        A submitted value containing a ``${NAME}`` reference is validated in
        its resolved form (so e.g. an integer field may hold ``${PORT}``) but
        persisted verbatim; only values without a reference are persisted in
        their normalized form. The response echoes the persisted values, never
        resolved secrets.
        """
        plugin_id = str(payload.get("plugin_id") or "").strip()
        values = payload.get("values")
        operation_id = payload.get("operation_id")
        if not plugin_id:
            raise RuntimeApplyError("runtime_invalid_request", "plugin_id 不能为空")
        if not isinstance(values, dict):
            raise RuntimeApplyError("runtime_invalid_request", "values 必须是对象")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise RuntimeApplyError("runtime_invalid_request", "操作 ID 不能为空")
        kernel = self._plugin_kernel()
        # 取出模型类并一路持有：本方法要等事务锁，期间可能有别的 apply 发布新
        # generation 并处置旧内核，届时再回查注册表会抛 KeyError（并发保存直接
        # 变成 internal_error）。模型类不可变，与 generation 无关。
        #
        # 已知的窄限制：这次模型查找发生在 apply() 的幂等 memo 检查之前，所以
        # 原样重试一次已成功的写入，若插件恰好在两次请求之间被卸载，会在这里
        # 因 model_cls is None 直接抛 plugin_config_unsupported，触不到 memo。
        # 没有把 memo 检查前移到这里，是因为 memo 的指纹取的是"校验后的
        # normalized 值"，而校验依赖这里的模型类——插件已卸载时二者都拿不到，
        # 没有一份不依赖模型、又能区分"这确实是同一次写入"的指纹可用；用未校验
        # 的原始 values 当指纹则会让一次成功写入和一次因校验规则变化而实际不同
        # 的写入无法区分。维持现状：卸载窗口内的重试被拒绝，而不是被静默放行。
        model_cls = (
            kernel.config_schemas.model_for(plugin_id) if kernel is not None else None
        )
        if model_cls is None:
            raise RuntimeApplyError(
                "plugin_config_unsupported",
                f"插件 {plugin_id} 未声明配置模型",
            )
        try:
            normalized = validate_against(model_cls, _resolved_table(values))
        except ValidationError as exc:
            raise RuntimeApplyError(
                "plugin_config_invalid",
                format_validation_error(exc),
                # details 会被 JSON 序列化写回 renderer：去掉 url 与 ctx，
                # 后者可能携带异常对象等不可序列化内容；也去掉 input，
                # 校验的是展开后的值，input 里可能正是环境变量里的密钥。
                errors=exc.errors(
                    include_url=False, include_context=False, include_input=False
                ),
            ) from exc
        persisted = _persisted_values(values, normalized)

        # 复用设置事务：定位-替换式合并 TOML 文本后走既有事务化落盘 + 热更新路径，
        # 不另起一套写盘逻辑（见 desktop_bridge/plugin_config_text.py）。
        # 合并与守卫都在事务锁内进行：本方法只改一张表、其余文本沿用"当前已提交
        # 的配置"，若在锁外读取基准文本，并发的 runtime.apply 会被整份覆盖掉。
        # 但当幂等 memo 命中时，apply() 根本不会调用这个回调——见
        # RuntimeSettingsApplication.apply 的文档。
        def _merge(current_text: str) -> str:
            # 启停状态与插件配置同住一张表，但它归宿主所有、不是配置模型的字段，
            # 校验时会被 pydantic 丢弃。整表替换必须把它显式带回来，否则用户改一次
            # 插件配置就会把停用的插件重新启用。
            values_to_write = dict(persisted)
            current = read_plugin_table(current_text, plugin_id)
            if PLUGIN_ENABLED_CONFIG_KEY in current:
                values_to_write[PLUGIN_ENABLED_CONFIG_KEY] = current[
                    PLUGIN_ENABLED_CONFIG_KEY
                ]
            try:
                merged = merge_plugin_table(current_text, plugin_id, values_to_write)
            except PluginTableConflict as exc:
                # 目标插件已经以本模块定位不到的形式存在于文档中（[plugins] 下的
                # 点分键，或内联表）：照常追加会生成重复的 [plugins.<id>] 声明，
                # 使整份文档无法解析，用户只会看到一个跟真实原因毫不相干的
                # "配置中存在无法用 TOML 表达的值"。这里直接给出能指导用户的错误。
                raise RuntimeApplyError(
                    "plugin_config_unrepresentable",
                    f"插件 {plugin_id} 的配置已经以点分键或内联表的形式写在 "
                    "[plugins] 表下，无法通过设置页定位替换；请先在配置文件中把它"
                    f"整理成独立的 [plugins.{plugin_id}] 表，再通过设置页保存",
                ) from exc
            self._assert_config_round_trip(
                model_cls,
                plugin_id,
                current_text,
                merged,
                normalized,
            )
            return merged

        apply_payload: dict[str, Any] = {"operation_id": operation_id}
        expected_generation = payload.get("expected_generation")
        if expected_generation is not None:
            apply_payload["expected_generation"] = expected_generation
        result = await self._settings.apply(
            apply_payload,
            prepare_service=prepare_service,
            publish_service=publish_service,
            # 幂等指纹按"本次逻辑操作"计算，而不是派生出来的整份配置文本：
            # 后者会随无关设置的变化而变，导致同一请求原样重试被误判为
            # runtime_operation_conflict。
            derive=DerivedWrite(
                build_config_toml=_merge,
                fingerprint_payload={"plugin_id": plugin_id, "values": persisted},
            ),
        )
        return {
            "plugin_id": plugin_id,
            "values": persisted,
            "env_status": _env_status(persisted),
            **result,
        }

    def _plugin_kernel(self) -> "PluginKernel | None":
        """Returns the currently published generation's plugin kernel, if any."""
        core = self._app.core
        return core.plugin_manager if core is not None else None

    @staticmethod
    def _assert_config_round_trip(
        model_cls: type[BaseModel],
        plugin_id: str,
        original_text: str,
        merged_text: str,
        normalized: dict[str, Any],
    ) -> None:
        """Rejects a merge that changed anything outside the target plugin's table.

        Two independent things can go wrong when text-splicing TOML:

        1. The TOML encoder cannot represent every JSON value (``None`` is
           dropped silently), or the target table's own shape round-trips
           into something the model no longer accepts.
        2. The line-scanning merge misidentifies the target table's span
           (e.g. a table header look-alike inside an unrelated multi-line
           value) and rewrites or drops content that belongs to a *different*
           table entirely.

        (2) is checked by the shared ``assert_plugin_table_isolated`` guard
        (also used by the plugin enable/disable toggle); (1) is specific to
        this schema-validated write, so it stays here as an extra check on
        top of that shared one.
        """

        stored = assert_plugin_table_isolated(plugin_id, original_text, merged_text)
        try:
            # 落盘的是未展开的引用，读回时与运行时加载一样先展开再校验。
            reread = validate_against(model_cls, _resolved_table(stored))
        except ValidationError as exc:
            raise RuntimeApplyError(
                "plugin_config_unrepresentable",
                f"配置写入后无法按模型读回: {format_validation_error(exc)}",
            ) from exc
        if reread != normalized:
            raise RuntimeApplyError(
                "plugin_config_unrepresentable",
                "配置中存在无法用 TOML 表达的值，写入已取消",
            )


def _persisted_values(
    submitted: dict[str, Any], normalized: dict[str, Any]
) -> dict[str, Any]:
    """Returns the table to write: normalized values, references kept verbatim.

    ``normalized`` was validated from the *resolved* submission, so any field
    whose submitted value holds a ``${NAME}`` reference carries the expanded
    secret there; that field is written back as submitted instead.
    """
    return {
        key: (
            submitted[key]
            if key in submitted and has_config_reference(submitted[key])
            else value
        )
        for key, value in normalized.items()
    }


def _env_status(values: dict[str, Any]) -> dict[str, str]:
    """Maps each top-level field holding a ``${NAME}`` reference to set/unset.

    ``"unset"`` means at least one reference in the field resolves from
    neither the environment nor the workspace memory file, so the plugin will
    see the literal placeholder at runtime.
    """
    return {
        key: (
            "unset" if has_config_reference(resolve_config_references(value)) else "set"
        )
        for key, value in values.items()
        if has_config_reference(value)
    }


def _resolved_table(values: dict[str, Any]) -> dict[str, Any]:
    """Returns ``values`` with every ``${NAME}`` reference expanded, for validation."""
    return {key: resolve_config_references(value) for key, value in values.items()}
