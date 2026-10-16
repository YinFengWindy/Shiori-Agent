"""Serial, recoverable settings application shared by all desktop callers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tomllib
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent.config import load_config_text
from agent.config_models import Config
from agent.plugin_host import (
    PluginReloadFailed,
    PluginReloadTimeout,
    PluginReloadUnsupported,
)
from bootstrap.app import AppRuntime
from core.roles.model_updates import prepare_role_model_updates
from core.roles.store import RoleStore
from desktop_bridge.config_transaction import ConfigTransaction

logger = logging.getLogger(__name__)

_RESULT_HISTORY_LIMIT = 64

# How long saving a plugin's config waits for that plugin's in-flight calls
# (tool calls, RPC/service calls, phase-module and tool-hook runs) before
# giving up with ``plugin_reload_busy``. Long enough for one ordinary plugin
# action to finish (browser_use bounds each browser action at 45 s), so a save
# made during such an action applies right after it instead of failing; much
# longer and the settings page would sit on "saving" with no feedback.
PLUGIN_RELOAD_DRAIN_TIMEOUT_SECONDS = 60.0


class RuntimeApplyError(ValueError):
    """A stable settings failure that never changes bridge health."""

    def __init__(self, error_code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = error_code
        self.details = details


def read_plugin_table(config_toml: str, plugin_id: str) -> dict[str, Any]:
    """Returns the ``[plugins.<plugin_id>]`` table from a config document.

    Callers that derive a new table from the current one need to read it
    inside the settings lock (see ``RuntimeSettingsApplication.apply``'s
    ``build_config_toml``), so they parse the text they were handed rather
    than the runtime's possibly-newer ``AppRuntime.config``.
    """

    try:
        document = tomllib.loads(config_toml)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeApplyError(
            "plugin_config_unrepresentable",
            f"当前配置无法解析: {exc}",
        ) from exc
    return dict(document.get("plugins", {}).get(plugin_id, {}))


def assert_plugin_table_isolated(
    plugin_id: str,
    original_text: str,
    merged_text: str,
) -> dict[str, Any]:
    """Rejects a ``[plugins.<plugin_id>]`` merge that touched anything else.

    Shared by every caller that text-splices one plugin's table
    (``plugin.config.set``, the plugin enable/disable toggle) so the same
    "parses both documents, only the target table may differ" guard is not
    reimplemented per caller. Schema-specific re-validation (pydantic
    round-trip) is the caller's own concern on top of this; this function
    only proves the merge did not corrupt anything *outside* the target
    table. Returns the merged document's own ``plugins.<plugin_id>`` table
    (``{}`` when absent) for the caller to validate further.
    """

    try:
        before = tomllib.loads(original_text)
    except tomllib.TOMLDecodeError as exc:
        # The pre-merge text is the config the runtime is already running
        # with, so a decode failure here indicates a bug upstream of this
        # module rather than a user mistake — but never assume anything
        # about it and refuse the write regardless.
        raise RuntimeApplyError(
            "plugin_config_unrepresentable",
            f"当前配置无法解析: {exc}",
        ) from exc
    try:
        after = tomllib.loads(merged_text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeApplyError(
            "plugin_config_unrepresentable",
            f"合并后的配置无法解析: {exc}",
        ) from exc
    if _without_plugin_table(before, plugin_id) != _without_plugin_table(
        after, plugin_id
    ):
        raise RuntimeApplyError(
            "plugin_config_unrepresentable",
            "合并后配置中出现了与目标插件无关的改动，写入已取消",
        )
    return dict(after.get("plugins", {}).get(plugin_id, {}))


def _without_plugin_table(document: dict[str, Any], plugin_id: str) -> dict[str, Any]:
    """Returns a shallow copy of ``document`` with ``plugins.<plugin_id>`` removed."""
    rest = dict(document)
    plugins = dict(rest.get("plugins", {}))
    plugins.pop(plugin_id, None)
    rest["plugins"] = plugins
    return rest


@dataclass(frozen=True, slots=True)
class DerivedWrite:
    """Bundles a text deriver with the fingerprint identifying its logical write.

    Some callers (e.g. ``plugin.config.set``) don't own a full draft; they
    derive the new config text from the currently committed text inside the
    apply lock instead of supplying it directly (see ``apply``'s docstring
    for why the derivation itself must run inside the lock).

    ``fingerprint_payload`` must describe that logical operation and be
    computable *without* running ``build_config_toml`` — that is the whole
    point of carrying it separately: it lets ``apply`` check idempotency
    before deriving, so a retry of an already-applied write still hits the
    remembered result even if deriving and merging again would now fail
    (e.g. the round-trip guard rejecting a merge against text that changed
    in the meantime). Bundling the two fields together, rather than passing
    them as independent optional parameters, keeps "this is a derived write"
    a single explicit concept a caller cannot supply half of.
    """

    build_config_toml: Callable[[str], str]
    fingerprint_payload: dict[str, Any]
    # Set when the derived text only replaces this plugin's ``[plugins.<id>]``
    # table: ``apply`` then reloads that plugin within the current generation
    # instead of swapping the generation, whenever the plugin allows it.
    reload_plugin: str | None = None


# (operation_id, generation, reloaded plugin ids) of one applied in-generation reload.
type PluginsReloadedListener = Callable[[str, int, tuple[str, ...]], None]


class RuntimeSettingsApplication:
    """Prepares candidates, commits persistence, and remembers idempotent results."""

    def __init__(
        self,
        app: AppRuntime,
        config_path: Path,
        role_store: RoleStore,
        *,
        on_plugins_reloaded: PluginsReloadedListener | None = None,
    ) -> None:
        self.app = app
        # Told synchronously, inside the reload's uninterruptible commit, which
        # plugins an operation reloaded; called once per applied reload.
        self._on_plugins_reloaded = on_plugins_reloaded
        self.roles = role_store
        self.transaction = ConfigTransaction(config_path, role_store.workspace)
        self.config_text = config_path.read_text(encoding="utf-8")
        self._lock = asyncio.Lock()
        self._results: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()

    async def apply(
        self,
        payload: dict[str, Any],
        *,
        prepare_service: Callable,
        publish_service: Callable,
        derive: DerivedWrite | None = None,
    ) -> dict[str, Any]:
        """Applies a complete draft once; failures leave draft ownership with the UI.

        A caller that derives its new text from the *current* committed text
        (rather than owning a full draft, as the settings UI does) passes
        ``derive``: ``derive.build_config_toml`` runs inside this lock, so a
        concurrent apply cannot slip a commit in between reading the current
        text and writing the derived one. Deriving outside the lock would
        silently drop the other writer's changes.

        The idempotency memo is checked *before* deriving, not after: a
        derived write's fingerprint is computed from ``derive.fingerprint_payload``,
        which needs no materialized text, so there is no reason to run the
        (possibly now-failing) derivation just to discover the request was
        already applied. Checking after derivation — as this used to — means
        a plain retry can fail the round-trip guard if the committed text
        changed in the meantime, instead of returning the remembered result.
        """
        async with self._lock:
            operation_id = payload.get("operation_id")
            updates = payload.get("role_model_updates", [])
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise RuntimeApplyError(
                    "runtime_invalid_request", "配置内容和操作 ID 不能为空"
                )
            if not isinstance(updates, list) or any(
                not isinstance(item, dict) for item in updates
            ):
                raise RuntimeApplyError(
                    "runtime_invalid_request", "角色模型更新必须是数组"
                )
            if derive is not None:
                fingerprint = self._fingerprint(derive.fingerprint_payload, updates)
            else:
                text = payload.get("config_toml")
                if not isinstance(text, str):
                    raise RuntimeApplyError(
                        "runtime_invalid_request", "配置内容不能为空"
                    )
                fingerprint = self._fingerprint(text, updates)
            memoized = self._check_memo(operation_id, fingerprint)
            if memoized is not None:
                return memoized
            if derive is not None:
                derived_text = derive.build_config_toml(self.config_text)
                payload = {**payload, "config_toml": derived_text}
            return await self._apply(
                operation_id,
                payload,
                prepare_service,
                publish_service,
                fingerprint,
                reload_plugin=derive.reload_plugin if derive is not None else None,
            )

    @staticmethod
    def _fingerprint(
        identity: str | dict[str, Any],
        updates: list[dict[str, Any]],
    ) -> str:
        """Hashes an operation's identity plus role updates into a retry fingerprint.

        ``identity`` is either the full draft text, or a derived write's
        logical payload — never the text a derived write *produces*, which
        would drift with unrelated concurrent settings changes and defeat
        idempotent retries (see ``DerivedWrite``).
        """
        try:
            encoded = json.dumps(
                {"identity": identity, "updates": updates},
                sort_keys=True,
                ensure_ascii=False,
            )
        except TypeError as exc:
            raise RuntimeApplyError(
                "runtime_invalid_request",
                f"操作载荷无法序列化: {exc}",
            ) from exc
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _check_memo(self, operation_id: str, fingerprint: str) -> dict[str, Any] | None:
        """Returns the remembered result for a byte-identical retry, else None.

        Raises when ``operation_id`` was already used for a *different*
        logical write, so retries can never silently reuse another
        operation's remembered result.
        """
        previous = self._results.get(operation_id)
        if previous is None:
            return None
        if previous[0] != fingerprint:
            raise RuntimeApplyError(
                "runtime_operation_conflict", "操作 ID 已用于其他配置"
            )
        return previous[1]

    async def _apply(
        self,
        operation_id: str,
        payload: dict[str, Any],
        prepare_service: Callable,
        publish_service: Callable,
        fingerprint: str,
        *,
        reload_plugin: str | None = None,
    ) -> dict[str, Any]:
        text = payload["config_toml"]
        updates = payload.get("role_model_updates", [])
        generation = self.app.generation
        expected = payload.get("expected_generation")
        if expected is not None and (
            type(expected) is not int or expected != generation
        ):
            raise RuntimeApplyError(
                "runtime_generation_conflict",
                "配置已更新，请重新读取后保存",
                generation=generation,
            )
        try:
            config = load_config_text(text)
            prepare_role_model_updates(
                self.roles, updates, {item.id for item in config.model_registrations}
            )
        except (ValueError, TypeError) as exc:
            raise RuntimeApplyError("runtime_config_invalid", str(exc)) from exc
        if config == self.app.config:
            with self.roles.lock:
                self._commit(
                    text,
                    lambda: prepare_role_model_updates(
                        self.roles,
                        updates,
                        {item.id for item in config.model_registrations},
                    ),
                )
            result = {"generation": generation, "changed": bool(updates)}
            self._remember(operation_id, fingerprint, result)
            return result
        if reload_plugin is not None and not updates:
            reloaded = await self._reload_plugin(
                reload_plugin, config, text, operation_id, fingerprint
            )
            if reloaded is not None:
                return reloaded
        candidate = None
        service = None
        try:
            candidate = await self.app.prepare(config)
            service = prepare_service(candidate.core)

            def commit() -> None:
                # Read the current role records again after asynchronous preparation.
                # Only model fields are merged, so intervening state is retained.
                with self.roles.lock:
                    roles_payload = prepare_role_model_updates(
                        self.roles,
                        updates,
                        {item.id for item in config.model_registrations},
                    )
                    self.transaction.commit(text, roles_payload)

            await self.app.publish(candidate, commit=commit)
        except BaseException as exc:
            try:
                if service is not None:
                    await service.aclose()
            finally:
                if candidate is not None:
                    await self.app.discard(candidate)
            if isinstance(exc, asyncio.CancelledError):
                raise
            details = exc.to_details() if hasattr(exc, "to_details") else {}
            raise RuntimeApplyError(
                getattr(exc, "code", "runtime_apply_failed"), str(exc), **details
            ) from exc
        self.config_text = text
        publish_service(service)
        result = {
            "generation": self.app.generation,
            "changed": self.app.generation != generation,
        }
        self._remember(operation_id, fingerprint, result)
        return result

    async def _reload_plugin(
        self,
        plugin_id: str,
        config: Config,
        text: str,
        operation_id: str,
        fingerprint: str,
    ) -> dict[str, Any] | None:
        """Applies a change confined to one plugin table without a generation swap.

        Reloads the plugin and its ACTIVE hard dependents in the published
        generation, or only stores the table of a disabled plugin. The live
        config tables, the committed text and the file change together or not
        at all: the commit runs inside the kernel's uninterruptible
        replacement, and a failed commit restores the old instances. Returns
        ``None`` when only a generation swap can apply the change (another part
        of the config differs, the closure has channels or cannot be hot
        unloaded, or the target is not ACTIVE).
        """
        current = self.app.config
        core = self.app.core
        kernel = core.plugin_manager if core is not None else None
        if kernel is None or _without_plugin(config, plugin_id) != _without_plugin(
            current, plugin_id
        ):
            return None
        values = config.plugins.get(plugin_id, {})
        raw_values = config.raw_plugin_configs.get(plugin_id, {})
        result: dict[str, Any] = {"generation": self.app.generation, "changed": False}

        def commit(plugin_ids: tuple[str, ...]) -> None:
            self._commit(text)
            if plugin_ids:
                result["reloaded_plugins"] = list(plugin_ids)
            self._remember(operation_id, fingerprint, result)
            if plugin_ids and self._on_plugins_reloaded is not None:
                self._on_plugins_reloaded(
                    operation_id, result["generation"], plugin_ids
                )

        try:
            reloaded = await kernel.reload(
                plugin_id,
                values=values,
                raw_values=raw_values,
                drain_timeout=PLUGIN_RELOAD_DRAIN_TIMEOUT_SECONDS,
                commit=commit,
            )
        except PluginReloadUnsupported as exc:
            if exc.reason == "disabled":
                # Nothing runs with these values; store them so a later enable
                # and every comparison against the live config see them. The
                # tables only change once the text is persisted.
                commit(())
                _store_plugin_tables(current, plugin_id, values, raw_values)
                return result
            if exc.reason == "retired":
                # The published kernel is only retired while the application
                # shuts down; a new generation must not be prepared then.
                raise RuntimeApplyError(
                    "runtime_generation_conflict",
                    "运行时正在关闭，配置未保存",
                    generation=self.app.generation,
                ) from exc
            return None
        except PluginReloadTimeout as exc:
            raise RuntimeApplyError(
                "plugin_reload_busy",
                f"插件 {', '.join(exc.busy) or plugin_id} 正在执行任务，"
                "新配置未保存，请稍后重试",
                plugin_ids=list(exc.busy),
            ) from exc
        except PluginReloadFailed as exc:
            if isinstance(cause := exc.__cause__, RuntimeApplyError):
                # The commit failed; the old config was restored, except for
                # the plugins in ``restore_failed`` (left FAILED).
                restore = (
                    f"\n插件 {', '.join(exc.restore_failed)} 未能按原配置恢复"
                    if exc.restore_failed
                    else ""
                )
                raise RuntimeApplyError(
                    cause.code,
                    f"{cause}{restore}",
                    **cause.details,
                    plugin_ids=list(exc.failed),
                    restore_failed=list(exc.restore_failed),
                ) from exc
            # First line: the kernel's summary (including whether the old
            # config came back); then each setup error, shown as detail.
            raise RuntimeApplyError(
                "plugin_reload_failed",
                f"{exc}，新配置未保存\n"
                + "\n".join(f"{key}: {error}" for key, error in exc.failed.items()),
                plugin_ids=list(exc.failed),
                restore_failed=list(exc.restore_failed),
            ) from exc
        for error in reloaded.cleanup_errors:
            logger.warning("插件重载后的清理失败: %s", error, exc_info=error)
        return result

    def _commit(
        self, text: str, roles_payload: Callable[[], dict | None] | None = None
    ) -> None:
        """Durably commits ``text`` (and role records) as the committed config.

        Any failure surfaces as ``runtime_commit_failed`` with both files
        restored by the transaction.
        """
        try:
            self.transaction.commit(
                text, roles_payload() if roles_payload is not None else None
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeApplyError("runtime_commit_failed", str(exc)) from exc
        self.config_text = text

    def _remember(
        self, operation_id: str, fingerprint: str, result: dict[str, Any]
    ) -> None:
        # Retries arrive shortly after the original attempt; a bounded window
        # keeps idempotency without growing for the lifetime of the bridge.
        self._results[operation_id] = fingerprint, result
        while len(self._results) > _RESULT_HISTORY_LIMIT:
            self._results.popitem(last=False)


def _without_plugin(config: Config, plugin_id: str) -> Config:
    """Returns ``config`` without one plugin's tables, to compare everything else."""
    return replace(
        config,
        plugins={
            key: value for key, value in config.plugins.items() if key != plugin_id
        },
        raw_plugin_configs={
            key: value
            for key, value in config.raw_plugin_configs.items()
            if key != plugin_id
        },
    )


def _store_plugin_tables(
    config: Config,
    plugin_id: str,
    values: dict[str, Any],
    raw_values: dict[str, Any],
) -> None:
    """Replaces one plugin's tables in the live config shared with the kernel."""
    config.plugins[plugin_id] = values
    config.raw_plugin_configs[plugin_id] = raw_values
