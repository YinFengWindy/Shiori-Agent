"""A stable bridge endpoint routing work to leased runtime generations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from bootstrap.app import AppRuntime
from bootstrap.runtime.generations import RuntimeLease
from core.common.cleanup import run_cleanup_steps
from core.roles import RoleStore
from core.common.runtime_scope import bind_runtime
from core.common.task_collector import TaskCollector
from desktop_bridge.method_policy import (
    Handler,
    MethodPolicy,
    OwnerRouting,
    resolve_plugin_method_policy,
)
from desktop_bridge.models import BridgeError, BridgeResponse
from desktop_bridge.runtime.apply import RuntimeApplyError, RuntimeSettingsApplication
from desktop_bridge.runtime.factory import build_desktop_service
from desktop_bridge.runtime.plugin_config import RuntimePluginConfig
from desktop_bridge.runtime.plugin_management import RuntimePluginManagement
from desktop_bridge.runtime.role_tasks import RuntimeRoleTasks
from desktop_bridge.runtime.settings_form import settings_form_write
from desktop_bridge.service import DesktopBridgeService

if TYPE_CHECKING:
    from agent.plugin_host.rpc import PluginRpcRegistry

logger = logging.getLogger(__name__)


@dataclass
class _ServiceGeneration:
    service: DesktopBridgeService
    lease: RuntimeLease
    publication_pending: bool = False
    requests: int = 0
    idle: asyncio.Event = field(default_factory=asyncio.Event)


class ReloadableDesktopService:
    """Keeps bridge identity and cancellation ownership stable across settings saves."""

    def __init__(self, app: AppRuntime, config_path: Path, roles: RoleStore) -> None:
        self.app = app
        self.roles = roles
        self.settings = RuntimeSettingsApplication(app, config_path, roles)
        self.role_tasks = RuntimeRoleTasks(app, roles)
        self.plugin_config = RuntimePluginConfig(app, self.settings)
        self.plugin_management = RuntimePluginManagement(app, self.settings)
        lease = app.pin()
        self._current = _ServiceGeneration(
            build_desktop_service(lease.core, roles), lease
        )
        self._entries = [self._current]
        self._listeners: set = set()
        self._retirements = TaskCollector("Desktop runtime retirement")

    @property
    def has_event_listeners(self) -> bool:
        """Reports whether the persistent desktop transport is connected."""
        return bool(self._listeners)

    def add_event_listener(self, listener) -> None:
        """Connects the same transport to current and draining generations."""
        self._listeners.add(listener)
        for entry in self._entries:
            entry.service.add_event_listener(listener)

    def remove_event_listener(self, listener) -> None:
        """Detaches a transport without affecting any running task."""
        self._listeners.discard(listener)
        for entry in self._entries:
            entry.service.remove_event_listener(listener)

    async def publish_event(self, payload) -> None:
        """Publishes host events through the currently connected transport."""
        await self._current.service.publish_event(payload)

    def start_background_tasks(self) -> None:
        """Starts initial bridge maintenance once the stream is ready."""
        self._current.service.start_background_tasks()

    def status(self):
        """Returns the committed configuration and capability state in one snapshot."""
        resolver = self._current.service.model_resolver
        config = self.app.config
        return {
            "generation": self.app.generation,
            "config_toml": self.settings.config_text,
            "models_registered": bool(config.model_registrations),
            "roles": {
                role.id: (
                    resolver.availability(role.id) if resolver else {"available": False}
                )
                for role in self.roles.list_roles()
            },
        }

    async def handle(self, request, *, emit_event):
        """Pins ordinary requests and applies settings without replacing the endpoint."""
        method = str(request.get("method") or "")
        request_id = str(request.get("id") or "bridge-request")
        payload = request.get("payload") or {}
        if not isinstance(payload, dict):
            return BridgeResponse(
                request_id,
                "response",
                method,
                error=BridgeError("invalid_request", "payload 必须是对象"),
            )
        policy = self.resolve_method_policy(method)
        if policy.handler is Handler.SETTINGS:

            async def compute_settings_result():
                result = (
                    self.status()
                    if method == "runtime.status"
                    else await self.settings.apply(
                        payload,
                        prepare_service=self._prepare,
                        publish_service=self._publish,
                        derive=settings_form_write(payload),
                    )
                )
                if method == "runtime.apply":
                    await self._notify_applied(request_id, result)
                return result

            return await self._respond_or_apply_error(
                request_id, method, compute_settings_result
            )
        if policy.handler is Handler.PLUGIN_CONFIG:

            async def compute_plugin_config_result():
                result = (
                    self.plugin_config.get(payload)
                    if method == "plugin.config.get"
                    else await self.plugin_config.set(
                        payload,
                        prepare_service=self._prepare,
                        publish_service=self._publish,
                    )
                )

                if method == "plugin.config.set":
                    await self._notify_applied(request_id, result)
                return result

            return await self._respond_or_apply_error(
                request_id, method, compute_plugin_config_result
            )
        if policy.handler is Handler.PLUGIN_MANAGEMENT:

            async def compute_plugin_management_result():
                if method == "plugins.list":
                    return self.plugin_management.list(payload)
                if method == "channels.list":
                    return self.plugin_management.channels.list(payload)
                if method == "plugins.trust":
                    return self.plugin_management.trust.confirm(payload)
                if (
                    method.startswith("plugins.install.")
                    or method == "plugins.uninstall"
                ):
                    result = await self.plugin_management.packages.handle(
                        method,
                        payload,
                        prepare_service=self._prepare,
                        publish_service=self._publish,
                    )
                    # Also retire renderer/background/surface resources after a
                    # successful hot disable in the uninstall transaction.
                    await self._notify_applied(
                        request_id, {**result, "generation": self.app.generation}
                    )
                    return result
                if method == "plugins.activation.report":
                    result = await self.plugin_management.report_activation(payload)
                    if result["changed"]:
                        # Reuses the existing roster-changed broadcast every
                        # window already listens for (see
                        # `pluginRuntimeChanged`) rather than inventing a
                        # second signal: no generation swap happened, but the
                        # authoritative plugin state did change and every
                        # window's next `plugins.list()` must see it.
                        await self.publish_event(
                            {
                                "id": request_id,
                                "type": "event",
                                "method": "runtime.applied",
                                "payload": {
                                    "generation": self.app.generation,
                                    "changed": True,
                                },
                            }
                        )
                    return result
                result = await self.plugin_management.set_enabled(
                    payload,
                    prepare_service=self._prepare,
                    publish_service=self._publish,
                )
                await self._notify_applied(request_id, result)
                return result

            return await self._respond_or_apply_error(
                request_id, method, compute_plugin_management_result
            )
        if policy.handler is Handler.ROLE_TASKS:
            role_id = str(payload.get("role_id") or "")
            try:
                if method == "roles.tasks.list":
                    tasks = self.role_tasks.list_tasks(role_id)
                else:
                    tasks = await self.role_tasks.cancel_task(
                        role_id, str(payload.get("task_id") or "")
                    )
                    await self.publish_event(
                        {
                            "id": request_id,
                            "type": "event",
                            "method": "roles.tasks.updated",
                            "payload": {"role_id": role_id},
                        }
                    )
                return BridgeResponse(request_id, "response", method, {"tasks": tasks})
            except (KeyError, ValueError, RuntimeError) as error:
                return BridgeResponse(
                    request_id,
                    "response",
                    method,
                    error=BridgeError("invalid_request", str(error)),
                )
        if not policy.admission_exempt and not self.app.accepting_work:
            return BridgeResponse(
                request_id,
                "response",
                method,
                error=BridgeError("runtime_reloading", "正在更新渠道配置，请稍后重试"),
            )
        entry = self._owner(policy.owner_routing, payload)
        if method == "chat.send":
            session_key = f"role:{payload.get('role_id', '')}"
            if any(
                item.service.chat_service.is_busy(session_key) for item in self._entries
            ):
                return BridgeResponse(
                    request_id,
                    "response",
                    method,
                    error=BridgeError("chat_busy", "当前会话已有正在执行的聊天任务"),
                )
        entry.requests += 1
        entry.idle.clear()
        try:
            async with entry.lease.retain() as lease:
                with bind_runtime(lease):
                    return await entry.service.handle(request, emit_event=emit_event)
        finally:
            entry.requests -= 1
            if not entry.requests:
                entry.idle.set()

    async def _notify_applied(self, request_id, result):
        """Announces actual publication once, while preserving refresh-only events."""
        entry = self._current
        if result["generation"] != entry.lease.generation:
            # An idempotent retry can return a result from a retired generation.
            return
        changed = entry.publication_pending
        # Claim publication before yielding so simultaneous saves/retries cannot
        # invalidate renderer contexts twice for the same committed generation.
        entry.publication_pending = False
        await entry.service.publish_event(
            {
                "id": request_id,
                "type": "event",
                "method": "runtime.applied",
                "payload": {**result, "changed": changed},
            }
        )

    async def _respond_or_apply_error(self, request_id: str, method: str, compute):
        """Runs one SETTINGS/PLUGIN_CONFIG/PLUGIN_MANAGEMENT handler.

        These three branches share one shape: call into a runtime-apply-style
        helper, then turn a ``RuntimeApplyError`` into a structured
        ``BridgeError`` response. Centralized here so that shape is written
        once instead of once per branch.
        """
        try:
            result = await compute()
            return BridgeResponse(request_id, "response", method, result)
        except RuntimeApplyError as exc:
            return BridgeResponse(
                request_id,
                "response",
                method,
                error=BridgeError(exc.code, str(exc), exc.details),
            )

    def _owner(self, routing: OwnerRouting, payload):
        for entry in self._entries:
            service = entry.service
            if (
                routing is OwnerRouting.BUSY_CHAT_SESSION
                and service.chat_service.is_busy(str(payload.get("session_key") or ""))
            ):
                return entry
            if (
                routing is OwnerRouting.BUSY_VOICE_TURN
                and service.chat_service.owns_voice_turn(
                    str(payload.get("voice_turn_id") or "")
                )
            ):
                return entry
            if (
                routing is OwnerRouting.BUSY_VOICE_SYNTHESIS
                and service.voice_handler.owns_synthesis(
                    str(payload.get("voice_request_id") or "")
                )
            ):
                return entry
        return self._current

    def resolve_method_policy(self, method: str) -> MethodPolicy:
        """Resolves dispatch policy, consulting the active generation's RPC registry."""
        return resolve_plugin_method_policy(method, self._plugin_rpc_registry)

    def _plugin_rpc_registry(self) -> "PluginRpcRegistry | None":
        """Returns the active generation's plugin RPC registry, if any.

        Only called for ``plugin.<id>.<method>`` requests (see
        ``resolve_plugin_method_policy``); other methods never touch
        ``self.app.core``.
        """
        core = self.app.core
        kernel = core.plugin_manager if core is not None else None
        return kernel.rpc if kernel is not None else None

    def _prepare(self, core):
        service = build_desktop_service(core, self.roles, activate_transport=False)
        return service

    def _publish(self, service):
        previous = self._current
        if previous.service.plugin_rpc_registry is not None:
            previous.service.plugin_rpc_registry.communication.retire()
        self._current = _ServiceGeneration(
            service, self.app.pin(), publication_pending=True
        )
        service.register_desktop_push_channel(self.app.core.push_tool)
        self._entries.append(self._current)
        for listener in self._listeners:
            service.add_event_listener(listener)
        self._retirements.spawn(self._retire(previous), name="desktop-runtime-retire")

    async def _retire(self, entry):
        if entry.requests:
            await entry.idle.wait()
        await entry.service.chat_service.drain()
        kernel = entry.lease.core.plugin_manager
        if kernel is not None:
            await kernel.drain()
        try:
            await run_cleanup_steps(
                ("desktop.service.close", entry.service.aclose),
                ("desktop.runtime.release", entry.lease.release),
            )
        finally:
            self._entries.remove(entry)

    async def aclose(self) -> None:
        """Cancels tasks only when the desktop bridge itself is shutting down."""
        self._retirements.cancel_all()
        await self._retirements.drain()
        try:
            await run_cleanup_steps(
                *[
                    step
                    for entry in self._entries
                    for step in (
                        ("desktop.service.close", entry.service.aclose),
                        ("desktop.runtime.release", entry.lease.release),
                    )
                ]
            )
        finally:
            self._entries.clear()
        if self._retirements.errors:
            raise ExceptionGroup(
                "Desktop runtime retirement failed", self._retirements.errors
            )
