"""``plugin.desktop_pet.live.*`` RPCs: settings, run control and run status.

Every method takes ``role_id``. ``live.config.set`` takes the whole settings
document (``room_id``, ``reply_interval_seconds``, ``wait_timeout_seconds``)
and replaces it after validation, matching autosave. Run control returns the
run status, the same shape ``live.status`` serves.
"""

from __future__ import annotations

from typing import Any

from shiori_sdk.rpc import Concurrency, RpcCapability

from .live_config import LiveConfigStore
from .live_engine import LiveEngine
from .rpc import require_role_id

_CONFIG_FIELDS = ("room_id", "reply_interval_seconds", "wait_timeout_seconds")


def register_live_rpc(
    rpc: RpcCapability, engine: LiveEngine, configs: LiveConfigStore
) -> None:
    """Expose the live engine under the ``live.`` namespace."""

    async def config_get(payload: dict[str, Any]) -> dict[str, Any]:
        role_id = require_role_id(payload)
        engine.require_role(role_id)
        return configs.read(role_id).model_dump(mode="json")

    async def config_set(payload: dict[str, Any]) -> dict[str, Any]:
        role_id = require_role_id(payload)
        engine.require_role(role_id)
        values = {key: payload[key] for key in _CONFIG_FIELDS if key in payload}
        config = configs.write(role_id, values)
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
