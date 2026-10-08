from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generator, TypeVar
from uuid import uuid4
from bus.event_bus import EventBus
from bus.events_context import ContextWindowChanged

from .services import RoleRepository
from .store import RoleRecord

if TYPE_CHECKING:
    from .model_runtime import ModelPurpose, RoleModelRuntime, RoleModelSnapshot
    from .self_initializer import RoleSelfInitializer


T = TypeVar("T")


class RoleBusyError(RuntimeError):
    """Role work was refused because another operation holds or awaits the turn gate."""


def _required(value: str, field: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{field} 不能为空")
    return clean


def _role_config_version(role: RoleRecord) -> str:
    payload = json.dumps(role.to_dict(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RoleExecutionContext:
    """Immutable identity and routing contract for role-scoped work."""

    role_id: str
    role_config_version: str
    thread_id: str
    transport_channel: str
    transport_chat_id: str
    request_id: str
    delivery_key: str
    source: str
    work_kind: str
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        role: RoleRecord,
        thread_id: str,
        transport_channel: str,
        transport_chat_id: str,
        source: str,
        work_kind: str,
        request_id: str = "",
        delivery_key: str = "",
    ) -> "RoleExecutionContext":
        """Creates a validated context from the authoritative role snapshot."""

        now = datetime.now().astimezone().isoformat()
        return cls(
            role_id=_required(role.id, "role_id"),
            role_config_version=_role_config_version(role),
            thread_id=_required(thread_id, "thread_id"),
            transport_channel=_required(transport_channel, "transport_channel"),
            transport_chat_id=_required(transport_chat_id, "transport_chat_id"),
            request_id=str(request_id or uuid4().hex),
            delivery_key=str(delivery_key or uuid4().hex),
            source=_required(source, "source"),
            work_kind=_required(work_kind, "work_kind"),
            created_at=now,
        )

    def to_metadata(self) -> dict[str, str]:
        """Serializes the context for existing transport and persistence adapters."""

        return {
            "role_id": self.role_id,
            "role_config_version": self.role_config_version,
            "thread_id": self.thread_id,
            "transport_channel": self.transport_channel,
            "transport_chat_id": self.transport_chat_id,
            "request_id": self.request_id,
            "delivery_key": self.delivery_key,
            "role_source": self.source,
            "role_work_kind": self.work_kind,
            "role_context_created_at": self.created_at,
        }


@dataclass
class RoleExecutionState:
    """Keeps role arbitration stable across runtime configuration generations."""

    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Operations that hold or are waiting for ``turn_lock``. Between a release
    # and the next waiter waking the lock reads unlocked, but a claim remains.
    claims: int = 0
    active_work: int = 0
    tasks: set[asyncio.Task[object]] = field(default_factory=set)
    closing: bool = False


class RoleRuntime:
    """Owns one role's mutable execution boundaries inside a process."""

    def __init__(
        self,
        role: RoleRecord,
        *,
        model_resolver: RoleModelRuntime | None = None,
        execution_state: RoleExecutionState | None = None,
        self_initializer: RoleSelfInitializer | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._role = role
        self._model_resolver = model_resolver
        self._self_initializer = self_initializer
        self._event_bus = event_bus
        # A role session is shared by every transport, so all mutable role work
        # must enter one role-wide turn gate regardless of its source thread.
        self._execution = execution_state or RoleExecutionState()

    @property
    def role_id(self) -> str:
        """Returns the role this runtime owns."""

        return self._role.id

    @property
    def config_version(self) -> str:
        """Returns the newest role configuration snapshot observed by this runtime."""

        return _role_config_version(self._role)

    def refresh_role(self, role: RoleRecord) -> None:
        """Applies a role configuration update without replacing the runtime identity."""

        if role.id != self.role_id:
            raise ValueError("不能用其他角色配置刷新 RoleRuntime")
        self._role = role

    @property
    def active_work(self) -> int:
        """Returns the number of work items currently executing in this runtime."""

        return self._execution.active_work

    @property
    def busy(self) -> bool:
        """Whether a role operation holds or awaits the shared turn gate, across generations."""
        return self._execution.claims > 0 or self._execution.turn_lock.locked()

    @property
    def models_enabled(self) -> bool:
        """Returns whether this runtime can resolve role-owned model snapshots."""

        return self._model_resolver is not None

    @contextmanager
    def activate_model(
        self,
        purpose: ModelPurpose,
    ) -> Generator[RoleModelSnapshot]:
        """Activates one immutable model snapshot owned by this role runtime."""

        if self._execution.closing:
            raise RuntimeError(f"角色运行时已停止: {self.role_id}")
        if self._model_resolver is None:
            raise RuntimeError(f"角色运行时未配置模型能力: {self.role_id}")
        with self._model_resolver.activate(self.role_id, purpose) as snapshot:
            yield snapshot

    def begin_closing(self) -> None:
        """Rejects new work while existing handlers finish or are cancelled."""

        self._execution.closing = True

    def cancel_active_work(self) -> None:
        """Cancels all registered work before the runtime is reloaded or removed."""

        for task in tuple(self._execution.tasks):
            task.cancel()

    async def execute_thread(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
        *,
        reject_busy: bool = False,
        notify_context: bool = True,
    ) -> T:
        """Runs role work serially across all transport threads.

        Every operation, including a rejected one, publishes one context refresh
        after release. Only callers that cannot change the conversation (role
        state) or publish their own refresh (manual compaction) pass
        ``notify_context=False``.

        ``reject_busy`` refuses with ``RoleBusyError`` instead of waiting
        whenever any other operation holds or awaits the gate.
        """

        try:
            self._validate_context(context)
            if reject_busy and self.busy:
                raise RoleBusyError("当前角色正在回复或整理上下文，请稍后重试")
            self._execution.claims += 1
            try:
                async with self._execution.turn_lock:
                    self._validate_context(context)
                    self._execution.active_work += 1
                    task = asyncio.current_task()
                    if task is not None:
                        self._execution.tasks.add(task)
                    try:
                        return await operation()
                    finally:
                        if task is not None:
                            self._execution.tasks.discard(task)
                        self._execution.active_work -= 1
            finally:
                self._execution.claims -= 1
        finally:
            # Formal/proactive commits are observed while this gate is held.
            # Publish the refresh only after release, including failed work.
            if notify_context and self._event_bus is not None:
                await self._event_bus.observe(
                    ContextWindowChanged(f"role:{self.role_id}", "")
                )

    async def run_passive_turn(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
        *,
        reject_busy: bool = False,
    ) -> T:
        """Runs the role's inbound conversation capability.

        ``reject_busy`` raises ``RoleBusyError`` rather than queueing behind
        other role work (plugin-submitted external turns yield to user turns).
        """
        self._require_work_kind(context, "passive_turn")

        async def initialized_turn():
            if self._self_initializer is None:
                return await operation()
            with self.activate_model("chat") as snapshot:
                await self._self_initializer.ensure_seeded(self.role_id, snapshot)
            # Restore the accepted turn snapshot before entering the conversation.
            return await operation()

        return await self.execute_thread(
            context, initialized_turn, reject_busy=reject_busy
        )

    async def run_proactive_tick(
        self, context: RoleExecutionContext, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Runs the role's proactive capability."""
        self._require_work_kind(context, "proactive_tick")
        return await self.execute_thread(context, operation)

    async def run_background_task(
        self, context: RoleExecutionContext, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Runs the role's persisted or deferred background capability."""
        self._require_work_kind(context, "scheduled_job")
        return await self.execute_thread(context, operation)

    async def send_channel(
        self, context: RoleExecutionContext, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Runs a role-authorized channel send through its owning runtime."""
        return await self.execute_thread(context, operation)

    async def execute_role_state(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Serializes mutations to role-wide state such as relationship data."""

        return await self.execute_thread(context, operation, notify_context=False)

    def _validate_context(self, context: RoleExecutionContext) -> None:
        if self._execution.closing:
            raise RuntimeError(f"角色运行时已停止: {self.role_id}")
        if context.role_id != self.role_id:
            raise ValueError("RoleExecutionContext 角色与 RoleRuntime 不匹配")

    @staticmethod
    def _require_work_kind(context: RoleExecutionContext, expected: str) -> None:
        if context.work_kind != expected:
            raise ValueError(f"角色能力不接受工作类型: {context.work_kind}")


class RoleRuntimeRegistry:
    """Creates and validates the process-local runtimes that own role work."""

    def __init__(
        self,
        repository: RoleRepository,
        *,
        model_resolver: RoleModelRuntime | None = None,
        shared_execution: RoleRuntimeRegistry | None = None,
        self_initializer: RoleSelfInitializer | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._model_resolver = model_resolver
        self._self_initializer = self_initializer
        self._runtimes: dict[str, RoleRuntime] = {}
        self._lock = asyncio.Lock()
        self._execution_states = (
            shared_execution._execution_states if shared_execution else {}
        )

    @property
    def model_resolver(self) -> RoleModelRuntime | None:
        """Returns this generation's model resolver for lifecycle and bridge wiring."""
        return self._model_resolver

    @property
    def repository(self) -> RoleRepository:
        """Returns the role repository shared across runtime generations."""
        return self._repository

    async def get(self, role_id: str) -> RoleRuntime:
        """Returns the stable runtime for a role and refreshes its current configuration."""

        role = self._repository.get_required(role_id)
        async with self._lock:
            current = self._runtimes.get(role.id)
            if current is not None:
                current.refresh_role(role)
                return current
            execution = self._execution_states.setdefault(role.id, RoleExecutionState())
            runtime = RoleRuntime(
                role,
                model_resolver=self._model_resolver,
                execution_state=execution,
                self_initializer=self._self_initializer,
                event_bus=self._event_bus,
            )
            self._runtimes[role.id] = runtime
            return runtime

    def create_context(
        self,
        *,
        role_id: str,
        thread_id: str,
        transport_channel: str,
        transport_chat_id: str,
        source: str,
        work_kind: str,
        request_id: str = "",
        delivery_key: str = "",
    ) -> RoleExecutionContext:
        """Builds an authoritative context for a direct role-owned entrypoint."""

        return RoleExecutionContext.create(
            role=self._repository.get_required(role_id),
            thread_id=thread_id,
            transport_channel=transport_channel,
            transport_chat_id=transport_chat_id,
            source=source,
            work_kind=work_kind,
            request_id=request_id,
            delivery_key=delivery_key,
        )

    async def dispatch_passive_turn(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
        *,
        reject_busy: bool = False,
    ) -> T:
        """Dispatches the inbound conversation capability for a role.

        ``reject_busy``: see ``RoleRuntime.run_passive_turn``.
        """
        return await (await self.get(context.role_id)).run_passive_turn(
            context, operation, reject_busy=reject_busy
        )

    async def dispatch_proactive_tick(
        self, context: RoleExecutionContext, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Dispatches the proactive capability for a role."""
        return await (await self.get(context.role_id)).run_proactive_tick(
            context, operation
        )

    async def dispatch_background_task(
        self, context: RoleExecutionContext, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Dispatches a background capability for a role."""
        return await (await self.get(context.role_id)).run_background_task(
            context, operation
        )

    async def dispatch_role_state(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Runs a role-wide mutation through the runtime selected by its context."""

        runtime = await self.get(context.role_id)
        return await runtime.execute_role_state(context, operation)

    async def close(self, role_id: str) -> None:
        """Stops a role runtime after ensuring no work remains active."""

        clean_role_id = _required(role_id, "role_id")
        async with self._lock:
            runtime = self._runtimes.get(clean_role_id)
            if runtime is None:
                return
            runtime.begin_closing()
            runtime.cancel_active_work()
            if runtime.active_work:
                raise RuntimeError(f"角色运行时仍有运行中的工作: {clean_role_id}")
            self._runtimes.pop(clean_role_id, None)
            self._execution_states.pop(clean_role_id, None)

    async def close_all(self) -> None:
        """Stops every idle runtime during process shutdown."""

        for role_id in list(self._runtimes):
            await self.close(role_id)

    def context_from_metadata(
        self,
        metadata: dict[str, Any],
    ) -> RoleExecutionContext | None:
        """Restores a fully specified context from an existing transport envelope."""

        required_fields = (
            "role_id",
            "role_config_version",
            "thread_id",
            "transport_channel",
            "transport_chat_id",
            "request_id",
            "delivery_key",
            "role_source",
            "role_work_kind",
            "role_context_created_at",
        )
        if not all(str(metadata.get(field) or "").strip() for field in required_fields):
            return None
        return RoleExecutionContext(
            role_id=str(metadata["role_id"]),
            role_config_version=str(metadata["role_config_version"]),
            thread_id=str(metadata["thread_id"]),
            transport_channel=str(metadata["transport_channel"]),
            transport_chat_id=str(metadata["transport_chat_id"]),
            request_id=str(metadata["request_id"]),
            delivery_key=str(metadata["delivery_key"]),
            source=str(metadata["role_source"]),
            work_kind=str(metadata["role_work_kind"]),
            created_at=str(metadata["role_context_created_at"]),
        )
