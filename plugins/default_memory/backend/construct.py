"""Build the default engine from this plugin's own config and injected ports.

Embedding credentials are only the plugin config (``${NAME}`` resolved at
setup; a reference that resolves to nothing counts as missing). Chat model
credentials are not a fallback. A missing credential, a missing main model or
a vector-space mismatch raises before the database is touched or changed, so
the kernel marks the plugin FAILED and leaves ``MEMORY_ENGINE`` empty.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

from shiori_sdk.core.models import MAIN_MODEL, MAIN_PROVIDER
from shiori_sdk.extensions import ConfigValues
from shiori_sdk.http import HttpClient
from shiori_sdk.memory.access import MemoryEvents
from shiori_sdk.memory.events import MemoryWritten
from shiori_sdk.models import ChatProvider
from shiori_sdk.runtime import Dispose, EventHandler, PluginRuntimeContext
from shiori_sdk.core.services import (
    CONFIG,
    EVENTS,
    HTTP,
    LIGHT_MODEL,
    LIGHT_PROVIDER,
    MEMORY,
)

from .config import (
    DefaultMemoryPluginConfig,
    ensure_default_memory_config_file,
    load_default_memory_config,
    resolve_memory_db_path,
)
from .engine.lifecycle import DefaultMemoryEngine
from .fingerprint import ensure_embedding_fingerprint
from .semantic.store import VEC_DIM

# What the host resolver leaves in place when ``${NAME}`` has no value; same
# pattern as the host's ``_CONFIG_REFERENCE``.
_UNRESOLVED_REFERENCE = re.compile(r"\$\{\w+\}")

_CREDENTIALS_MISSING = (
    "default_memory 未配置向量模型凭据"
    "（embedding_api_key、embedding_base_url 与 embedding_model），记忆引擎未启动"
)


class _EngineSetup(PluginRuntimeContext, Protocol):
    """Ports ``construct_default_engine`` reads off the plugin context."""

    @property
    def config(self) -> ConfigValues: ...
    @property
    def http(self) -> HttpClient: ...
    @property
    def light_provider(self) -> ChatProvider: ...
    @property
    def light_model(self) -> str: ...


def construct_default_engine(ctx: _EngineSetup) -> DefaultMemoryEngine:
    """Construct the engine and register its database and embedder for cleanup."""
    embedding_model, api_key, base_url, dimensionality = _embedding_settings(ctx)
    if not embedding_model or not api_key or not base_url:
        raise RuntimeError(_CREDENTIALS_MISSING)
    provider = ctx.require(MAIN_PROVIDER)
    model = ctx.require(MAIN_MODEL)
    workspace = ctx.require(MEMORY).workspace
    storage = ctx.require(MEMORY).storage
    ensure_default_memory_config_file(workspace=workspace, storage=storage)
    default_config = load_default_memory_config(workspace=workspace, storage=storage)
    db_path = resolve_memory_db_path(workspace=workspace, default_config=default_config)
    dim = dimensionality if dimensionality is not None else VEC_DIM
    _prepare_database(storage.open_database, db_path, model=embedding_model, dim=dim)

    def register(resource: object, cleanup: Dispose) -> None:
        ctx.effect(type(resource).__name__, cleanup)

    return DefaultMemoryEngine(
        model=model,
        light_model=ctx.require(LIGHT_MODEL),
        embedding_base_url=base_url,
        embedding_api_key=api_key,
        embedding_model=embedding_model,
        output_dimensionality=dimensionality,
        default_config=default_config,
        workspace=workspace,
        provider=provider,
        light_provider=ctx.require(LIGHT_PROVIDER),
        requester=ctx.require(HTTP),
        storage=storage,
        roles=ctx.require(MEMORY).roles,
        skills=ctx.require(MEMORY).skill_names,
        register=register,
        event_publisher=_WatchingMemoryEvents(
            cast(MemoryEvents, ctx.require(EVENTS)), ctx.emit
        ),
    )


class _WatchingMemoryEvents:
    """Bus publisher that also emits a watch-safe ``MemoryWritten`` on the kernel.

    The bus copy keeps ``superseded_ids`` as a list. The kernel copy is a tuple,
    because ``kernel.emit`` rejects a list field. Other events stay on the bus:
    ``TurnCommitted`` is bus-only in P3, and ``TurnIngested`` is not watched.
    """

    def __init__(
        self,
        events: MemoryEvents,
        emit: Callable[[object], Awaitable[object]],
    ) -> None:
        self._events = events
        self._emit = emit

    def on[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None:
        self._events.on(event_type, handler)

    def off[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None:
        self._events.off(event_type, handler)

    async def emit[EventT](self, event: EventT) -> EventT:
        return await self._events.emit(event)

    def enqueue(self, event: object) -> None:
        self._events.enqueue(event)

    async def fanout(self, event: object) -> None:
        await fanout_memory_observation(self._events, self._emit, event)


async def fanout_memory_observation(
    events: MemoryEvents,
    emit: Callable[[object], Awaitable[object]],
    event: object,
) -> None:
    """Fan the original out on the bus, then emit a frozen ``MemoryWritten``.

    The frozen copy is taken first, so bus listeners cannot change what
    watchers see. The bus goes first: its observer failures are only logged,
    while ``emit`` can raise, so a failing emit never drops the bus delivery.
    """
    frozen = (
        replace(event, superseded_ids=tuple(event.superseded_ids))
        if isinstance(event, MemoryWritten)
        else None
    )
    await events.fanout(event)
    if frozen is not None:
        await emit(frozen)


def _embedding_settings(ctx: _EngineSetup) -> tuple[str, str, str, int | None]:
    settings = DefaultMemoryPluginConfig.model_validate(ctx.require(CONFIG).as_dict())

    def resolve(value: str) -> str:
        resolved = ctx.require(CONFIG).resolve_reference(value).strip()
        # Any reference left over, even inside ``${BASE}/v1``, means missing.
        return "" if _UNRESOLVED_REFERENCE.search(resolved) else resolved

    return (
        resolve(settings.embedding_model),
        resolve(settings.embedding_api_key),
        resolve(settings.embedding_base_url),
        settings.output_dimensionality,
    )


def _prepare_database(
    open_database: Callable[[Path], sqlite3.Connection],
    db_path: Path,
    *,
    model: str,
    dim: int,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = open_database(db_path)
    try:
        ensure_embedding_fingerprint(connection, model=model, dim=dim)
    finally:
        connection.close()
