"""The process-wide proactive loops, shared by every generation of the plugin.

Each generation's setup attaches its host services (a ``ProactiveBinding``)
and does not start role loops. ``published`` (``PROCESS_RESOURCES.on_published``)
and the role create and delete events reconcile: every role has one loop,
built and rebound on the published binding only. A candidate that is set up
and then discarded changes nothing.

A loop rereads its role's ``proactive`` settings before every tick: a role
whose switch is off skips the tick and holds no state store or MCP sessions,
and a changed config applies from the next tick.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shiori_sdk.core.affection import Affection
from shiori_sdk.core.conversation import Conversation
from shiori_sdk.core.markdown_memory import MarkdownMemory
from shiori_sdk.core.proactive_host import ProactiveHost
from shiori_sdk.core.sessions import Presence
from shiori_sdk.memory.engine import MemoryEngine, MemoryQuery, MemoryQueryResult
from shiori_sdk.processes import Processes
from shiori_sdk.roles import Roles

from .config import ProactiveConfig
from .config_loader import load_proactive_config
from .loop import ProactiveLoop
from .session_key import role_session_key
from .turn.gates import ProactiveGate
from .turn.strategies import (
    RelationshipStrategy,
    SceneFollowupStrategy,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)
class ProactiveBinding:
    """One generation's host services.

    ``is_active`` is true only while this generation is the published one.
    ``draft_prompt`` reads that generation's natural-chat draft, or returns
    None when the policy plugin is off.
    """

    host: ProactiveHost
    conversation: Conversation
    roles: Roles
    processes: Processes
    workspace: Path
    presence: Presence | None
    markdown: MarkdownMemory
    memory_engine: MemoryEngine | None
    scene_followup: bool
    relationship: bool
    affection: Affection | None
    draft_prompt: Callable[[], str | None]
    is_active: Callable[[], bool]


class _Sessions:
    """The workspace and role session key a loop reads. Nothing else."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def role_session_key(self, role_id: str) -> str:
        return role_session_key(role_id)


class _RoleMemory:
    """One role loop's memory: markdown documents plus this generation's engine.

    ``bind_session_metadata`` selects the role the next document read uses.
    Each loop has its own adapter, so two roles' ticks do not share that choice.
    """

    def __init__(self, markdown: MarkdownMemory, engine: MemoryEngine | None) -> None:
        self._markdown = markdown
        self._engine = engine
        self._role_id: str | None = None

    def bind_session_metadata(self, metadata: Mapping[str, Any] | None) -> None:
        role_id = None
        if isinstance(metadata, Mapping):
            raw = metadata.get("role_id")
            role_id = str(raw).strip() if raw else None
        self._role_id = role_id or None

    def _documents(self):
        if not self._role_id:
            return None
        return self._markdown.role(self._role_id)

    def read_long_term(self) -> str:
        documents = self._documents()
        return documents.read_long_term() if documents is not None else ""

    def read_self(self) -> str:
        documents = self._documents()
        return documents.read_self() if documents is not None else ""

    def read_recent_context(self) -> str:
        documents = self._documents()
        return documents.read_recent_context() if documents is not None else ""

    async def query(self, request: MemoryQuery) -> MemoryQueryResult:
        if self._engine is None:
            return MemoryQueryResult()
        return await self._engine.query(request)


@dataclass
class _Running:
    loop: Any
    task: asyncio.Task[None]


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def role_proactive_config(
    role_id: str, settings: Mapping[str, object]
) -> ProactiveConfig:
    """The runtime config from one role's ``proactive`` settings."""
    agent = dict(_mapping(settings.get("agent")))
    agent.pop("model", None)
    return load_proactive_config(
        {
            "enabled": bool(settings.get("enabled")),
            "profile": str(settings.get("profile") or "daily"),
            "overrides": dict(_mapping(settings.get("overrides"))),
            "agent": agent,
            "drift": dict(_mapping(settings.get("drift"))),
        },
        role_id=role_id,
    )


def _read_config(role_id: str) -> Callable[[Roles], ProactiveConfig]:
    def read(roles: Roles) -> ProactiveConfig:
        settings = roles.plugin_settings(role_id, "proactive").read()
        return role_proactive_config(role_id, settings)

    return read


def _role_prompt(host: ProactiveHost, role_id: str) -> Callable[[], str]:
    def resolve() -> str:
        return host.compile_role_prompt(role_id)

    return resolve


def _passive_busy(host: ProactiveHost, role_id: str) -> Callable[[str], bool]:
    def busy(_session_key: str) -> bool:
        return host.passive_turn_busy(role_id)

    return busy


def _tick(host: ProactiveHost, role_id: str):
    async def dispatch(operation):
        return await host.run_tick(role_id, operation)

    return dispatch


def _affection_prompt(
    binding: ProactiveBinding, role_id: str
) -> Callable[[], str | None]:
    def render() -> str | None:
        affection = binding.affection
        if affection is None:
            return None
        return affection.render_prompt(role_id)

    return render


def _motives(binding: ProactiveBinding) -> list[ProactiveGate]:
    def source() -> Affection | None:
        return binding.affection

    motives: list[ProactiveGate] = []
    if binding.scene_followup:
        motives.append(SceneFollowupStrategy(source))
    if binding.relationship:
        motives.append(RelationshipStrategy(source))
    return motives


class ProactiveService:
    """One proactive loop per role for the process. Idle until a generation is published.

    A loop that dies is logged, the other roles keep running, and the next
    reconcile (publication, role created or deleted) starts that role again.
    ``close`` raises the failure so the host does not leave the plugin
    ACTIVE with a dead loop unreported. ``loop_factory`` builds a role's
    loop (``ProactiveLoop``'s signature).
    """

    def __init__(self, *, loop_factory: Callable[..., Any] | None = None) -> None:
        self._loop_factory = loop_factory or ProactiveLoop
        self._bindings: list[ProactiveBinding] = []
        self._loops: dict[str, _Running] = {}
        # Stopped loops of a role still winding down; its next loop waits
        # for all of them, so two loops of one role never overlap.
        self._stopping: dict[str, set[asyncio.Task[None]]] = {}
        self._failures: list[BaseException] = []
        self._closed = False

    def attach(self, binding: ProactiveBinding) -> Callable[[], None]:
        """Stores a generation's services. Does not start or rebind loops."""
        if self._closed:
            raise RuntimeError("主动循环服务已关闭")
        self._bindings.append(binding)
        return lambda: self._detach(binding)

    def published(self) -> None:
        """The attaching generation was published. Reconcile on its binding."""
        self._reconcile()

    def on_roles_changed(self) -> None:
        """A role was created or deleted."""
        self._reconcile()

    async def close(self) -> None:
        """Stops every role loop and raises a loop that died on its own."""
        self._closed = True
        self._bindings.clear()
        for role_id in list(self._loops):
            self._stop_role(role_id)
        tasks = {task for pending in self._stopping.values() for task in pending}
        if tasks:
            _ = await asyncio.wait(tasks)
        if not self._failures:
            return
        errors, self._failures = self._failures, []
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup("主动循环异常退出", errors)

    def _detach(self, binding: ProactiveBinding) -> None:
        if binding in self._bindings:
            self._bindings.remove(binding)

    def _active_binding(self) -> ProactiveBinding | None:
        active = [binding for binding in self._bindings if binding.is_active()]
        return active[-1] if active else None

    def _reconcile(self) -> None:
        if self._closed:
            return
        binding = self._active_binding()
        if binding is None:
            return
        role_ids = [role.id for role in binding.roles.list_roles()]
        for role_id in list(self._loops):
            if role_id not in role_ids:
                self._stop_role(role_id)
        max_tokens = binding.host.configured_max_tokens()
        for role_id in role_ids:
            running = self._loops.get(role_id)
            if running is not None and running.task.done():
                # Died (already logged and kept for ``close``): start anew.
                del self._loops[role_id]
                running = None
            if running is None:
                self._start_role(binding, role_id, max_tokens)
                continue
            running.loop.rebind(
                sessions=_Sessions(binding.workspace),
                processes=binding.processes,
                conversation=binding.conversation,
                roles=binding.roles,
                max_tokens=max_tokens,
                memory_store=_RoleMemory(binding.markdown, binding.memory_engine),
                presence=binding.presence,
                proactive_motives=_motives(binding),
                role_prompt_fn=_role_prompt(binding.host, role_id),
                passive_busy_fn=_passive_busy(binding.host, role_id),
                affection_prompt_fn=_affection_prompt(binding, role_id),
                draft_prompt_fn=binding.draft_prompt,
            )

    def _start_role(
        self, binding: ProactiveBinding, role_id: str, max_tokens: int
    ) -> None:
        read_config = _read_config(role_id)
        loop = self._loop_factory(
            _Sessions(binding.workspace),
            read_config(binding.roles),
            proactive_host=binding.host,
            conversation=binding.conversation,
            roles=binding.roles,
            role_prompt_fn=_role_prompt(binding.host, role_id),
            state_path=binding.workspace / "roles" / role_id / "proactive.db",
            processes=binding.processes,
            config_fn=read_config,
            max_tokens=max_tokens,
            memory_store=_RoleMemory(binding.markdown, binding.memory_engine),
            presence=binding.presence,
            passive_busy_fn=_passive_busy(binding.host, role_id),
            proactive_motives=_motives(binding),
            tick_dispatcher=_tick(binding.host, role_id),
            affection_prompt_fn=_affection_prompt(binding, role_id),
            draft_prompt_fn=binding.draft_prompt,
        )
        prior = frozenset(self._stopping.get(role_id, ()))
        # A fresh context: the loop outlives the request or event that started
        # it, and must not keep that request's runtime lease.
        task = asyncio.create_task(
            self._run_role(role_id, loop, prior),
            name=f"proactive:{role_id}",
            context=contextvars.Context(),
        )
        self._loops[role_id] = _Running(loop, task)

    def _stop_role(self, role_id: str) -> None:
        running = self._loops.pop(role_id, None)
        if running is None:
            return
        running.loop.stop()
        _ = running.task.cancel()
        if running.task.done():
            return
        pending = self._stopping.setdefault(role_id, set())
        pending.add(running.task)

        def finished(task: asyncio.Task[None]) -> None:
            pending.discard(task)
            if not pending and self._stopping.get(role_id) is pending:
                del self._stopping[role_id]

        running.task.add_done_callback(finished)

    async def _run_role(
        self, role_id: str, loop: Any, prior: frozenset[asyncio.Task[None]]
    ) -> None:
        if prior:
            _ = await asyncio.wait(prior)
        try:
            await loop.run()
        except asyncio.CancelledError as error:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            # Nobody stopped this loop: a cancellation leaked out of it.
            logger.error("[proactive] 角色循环被意外取消 role=%s", role_id)
            failure = RuntimeError(f"主动循环被意外取消: {role_id}")
            failure.__cause__ = error
            self._failures.append(failure)
        except Exception as error:
            logger.exception("[proactive] 角色循环异常退出 role=%s", role_id)
            self._failures.append(error)
