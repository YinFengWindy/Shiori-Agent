"""``plugin.desktop_pet.live.*`` RPCs: settings, run control and run status.

Every method takes ``role_id``. ``live.config.set`` changes only the fields it
is given (``room_id``, ``reply_interval_seconds``, ``wait_timeout_seconds``),
so autosaving one field never resets another; invalid values fail with a
Chinese message and change nothing. A new room applies at the next start;
``live.status`` shows both ``configured_room_id`` and the running ``room``.
Run control returns the status, in the same shape ``live.status`` serves.
"""

from __future__ import annotations

from typing import Any

from shiori_sdk.rpc import Concurrency, RpcCapability

from .live_config import LiveConfigStore
from .live_engine import LiveEngine
from .rpc import require_role_id


def register_live_rpc(
    rpc: RpcCapability, engine: LiveEngine, configs: LiveConfigStore
) -> None:
    """Expose the live engine under the ``live.`` namespace."""

    async def config_get(payload: dict[str, Any]) -> dict[str, Any]:
        role_id = require_role_id(payload)
        engine.gate.require_role(role_id)
        return configs.read(role_id).model_dump(mode="json")

    async def config_set(payload: dict[str, Any]) -> dict[str, Any]:
        role_id = require_role_id(payload)
        engine.gate.require_role(role_id)
        changes = {key: value for key, value in payload.items() if key != "role_id"}
        config = configs.update(role_id, changes)
        engine.apply_config(role_id, config)
        return config.model_dump(mode="json")

    async def start(payload: dict[str, Any]) -> dict[str, Any]:
        return await engine.start(require_role_id(payload))

    async def pause(payload: dict[str, Any]) -> dict[str, Any]:
        return await engine.pause(require_role_id(payload))

    async def resume(payload: dict[str, Any]) -> dict[str, Any]:
        return await engine.resume(require_role_id(payload))

    async def stop(payload: dict[str, Any]) -> dict[str, Any]:
        return await engine.stop(require_role_id(payload))

    async def status(payload: dict[str, Any]) -> dict[str, Any]:
        return engine.status(require_role_id(payload))

    rpc.register("live.config.get", config_get, concurrency=Concurrency.READ_ONLY)
    rpc.register("live.config.set", config_set)
    # Starting validates the login and resolves the room with Bilibili.
    rpc.register("live.start", start, concurrency=Concurrency.INTEGRATION)
    rpc.register("live.pause", pause)
    rpc.register("live.resume", resume)
    rpc.register("live.stop", stop)
    rpc.register("live.status", status, concurrency=Concurrency.READ_ONLY)
