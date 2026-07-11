from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar
from uuid import uuid4

from .services import RoleRepository
from .store import RoleRecord


T = TypeVar("T")


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


class RoleWorld:
    """Owns one role's mutable execution boundaries inside a process."""

    def __init__(self, role: RoleRecord) -> None:
        self._role = role
        self._thread_locks: dict[str, asyncio.Lock] = {}
        self._state_lock = asyncio.Lock()
        self._active_work = 0
        self._tasks: set[asyncio.Task[object]] = set()
        self._closing = False

    @property
    def role_id(self) -> str:
        """Returns the role this world owns."""

        return self._role.id

    @property
    def config_version(self) -> str:
        """Returns the role snapshot version used to create this world."""

        return _role_config_version(self._role)

    @property
    def active_work(self) -> int:
        """Returns the number of work items currently executing in this world."""

        return self._active_work

    def begin_closing(self) -> None:
        """Rejects new work while existing handlers finish or are cancelled."""

        self._closing = True

    def cancel_active_work(self) -> None:
        """Cancels all registered work before the world is reloaded or removed."""

        for task in tuple(self._tasks):
            task.cancel()

    async def execute_thread(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Runs a turn serially within its thread and never across world versions."""

        self._validate_context(context)
        lock = self._thread_locks.setdefault(context.thread_id, asyncio.Lock())
        async with lock:
            self._validate_context(context)
            self._active_work += 1
            task = asyncio.current_task()
            if task is not None:
                self._tasks.add(task)
            try:
                return await operation()
            finally:
                if task is not None:
                    self._tasks.discard(task)
                self._active_work -= 1

    async def execute_role_state(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Serializes mutations to role-wide state such as relationship data."""

        self._validate_context(context)
        async with self._state_lock:
            self._validate_context(context)
            self._active_work += 1
            task = asyncio.current_task()
            if task is not None:
                self._tasks.add(task)
            try:
                return await operation()
            finally:
                if task is not None:
                    self._tasks.discard(task)
                self._active_work -= 1

    def _validate_context(self, context: RoleExecutionContext) -> None:
        if self._closing:
            raise RuntimeError(f"角色世界已停止: {self.role_id}")
        if context.role_id != self.role_id:
            raise ValueError("RoleExecutionContext 角色与 RoleWorld 不匹配")
        if context.role_config_version != self.config_version:
            raise RuntimeError(f"角色配置已过期: {self.role_id}")


class RoleWorldRegistry:
    """Creates and validates the process-local worlds that own role work."""

    def __init__(self, repository: RoleRepository) -> None:
        self._repository = repository
        self._worlds: dict[str, RoleWorld] = {}
        self._lock = asyncio.Lock()

    async def get(self, role_id: str) -> RoleWorld:
        """Returns the current world for a role, replacing stale snapshots atomically."""

        role = self._repository.get_required(role_id)
        async with self._lock:
            current = self._worlds.get(role.id)
            if current is not None and current.config_version == _role_config_version(role):
                return current
            if current is not None:
                current.begin_closing()
                current.cancel_active_work()
                if current.active_work:
                    raise RuntimeError(f"角色世界正在重载: {role.id}")
            world = RoleWorld(role)
            self._worlds[role.id] = world
            return world

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

    async def dispatch_thread(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Runs a thread turn through the world selected by its explicit context."""

        world = await self.get(context.role_id)
        return await world.execute_thread(context, operation)

    async def dispatch_role_state(
        self,
        context: RoleExecutionContext,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Runs a role-wide mutation through the world selected by its context."""

        world = await self.get(context.role_id)
        return await world.execute_role_state(context, operation)

    async def close(self, role_id: str) -> None:
        """Stops a role world after ensuring no work remains active."""

        clean_role_id = _required(role_id, "role_id")
        async with self._lock:
            world = self._worlds.get(clean_role_id)
            if world is None:
                return
            world.begin_closing()
            world.cancel_active_work()
            if world.active_work:
                raise RuntimeError(f"角色世界仍有运行中的工作: {clean_role_id}")
            self._worlds.pop(clean_role_id, None)

    async def close_all(self) -> None:
        """Stops every idle world during process shutdown."""

        for role_id in list(self._worlds):
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
