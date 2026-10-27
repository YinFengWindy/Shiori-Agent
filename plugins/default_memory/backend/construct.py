"""Build the default engine from this plugin's own config and injected ports.

Embedding credentials are only the plugin config (``${NAME}`` resolved at
setup). Chat model credentials are not a fallback. A missing credential or a
vector-space mismatch raises, so the kernel marks the plugin FAILED and
leaves ``MEMORY_ENGINE`` empty.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from shiori_sdk.core.models import MAIN_MODEL, MAIN_PROVIDER
from shiori_sdk.extensions import ConfigValues
from shiori_sdk.http import HttpClient
from shiori_sdk.memory.access import MemoryEvents
from shiori_sdk.models import ChatProvider, ModelProvider
from shiori_sdk.runtime import Dispose, PluginRuntimeContext

from .config import (
    DefaultMemoryPluginConfig,
    ensure_default_memory_config_file,
    load_default_memory_config,
    resolve_memory_db_path,
)
from .engine.lifecycle import DefaultMemoryEngine
from .fingerprint import ensure_embedding_fingerprint
from .semantic.store import VEC_DIM

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
    workspace = ctx.memory.workspace
    storage = ctx.memory.storage
    ensure_default_memory_config_file(workspace=workspace, storage=storage)
    default_config = load_default_memory_config(workspace=workspace, storage=storage)
    db_path = resolve_memory_db_path(workspace=workspace, default_config=default_config)
    dim = dimensionality if dimensionality is not None else VEC_DIM
    _prepare_database(storage.open_database, db_path, model=embedding_model, dim=dim)
    provider = cast(ModelProvider, ctx.require(MAIN_PROVIDER))
    model = ctx.require(MAIN_MODEL)

    def register(resource: object, cleanup: Dispose) -> None:
        ctx.effect(type(resource).__name__, cleanup)

    return DefaultMemoryEngine(
        model=model,
        light_model=ctx.light_model or model,
        embedding_base_url=base_url,
        embedding_api_key=api_key,
        embedding_model=embedding_model,
        output_dimensionality=dimensionality,
        default_config=default_config,
        workspace=workspace,
        provider=provider,
        light_provider=ctx.light_provider,
        requester=ctx.http,
        storage=storage,
        roles=ctx.memory.roles,
        skills=ctx.memory.skill_names,
        register=register,
        event_publisher=cast(MemoryEvents, ctx.events),
    )


def _embedding_settings(ctx: _EngineSetup) -> tuple[str, str, str, int | None]:
    settings = DefaultMemoryPluginConfig.model_validate(ctx.config.as_dict())
    resolve = ctx.config.resolve_reference
    return (
        resolve(settings.embedding_model).strip(),
        resolve(settings.embedding_api_key).strip(),
        resolve(settings.embedding_base_url).strip(),
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
