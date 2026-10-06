"""Private configuration and reference RPCs; no role extensions or host config."""

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency
from shiori_sdk.managed.controller import ManagedRuntime

from .engine import SynthesisEngine
from .settings import RoleVoice


def register_rpc(
    ctx: ServicePluginContext, engine: SynthesisEngine, runtime: ManagedRuntime
) -> None:
    """Expose the plugin's settings and explicit role-save transaction."""
    store, references = engine.store, engine.references

    def require_role(params: dict[str, object]) -> str:
        role_id = params.get("role_id")
        if not isinstance(role_id, str) or ctx.roles.get_role(role_id) is None:
            raise ValueError("角色不存在，请先保存角色")
        return role_id

    async def get(_params: dict[str, object]):
        return store.read().settings.model_dump()

    async def save(params: dict[str, object]):
        if engine.lock.locked() or runtime.status()["busy"]:
            raise RuntimeError("请等待当前推理或环境操作结束后再保存连接设置")
        previous = store.read().settings.connection_mode
        result = store.save_settings(params)
        if previous != result.connection_mode:
            await runtime.stop()
            if result.connection_mode == "managed" and runtime.status()["installed"]:
                runtime.submit("start")
        return result.model_dump()

    async def health(_params: dict[str, object]):
        return {
            **await engine.client.health(engine.settings()),
            **engine.instance.status(),
        }

    async def role_get(params: dict[str, object]):
        with ctx.roles.read_scope():
            role_id = require_role(params)
            return store.read().roles.get(role_id, RoleVoice()).model_dump()

    async def role_save(params: dict[str, object]):
        with ctx.roles.read_scope():
            role_id = require_role(params)
            voice = RoleVoice.model_validate(params.get("voice"))
            references.validate(voice)
            references.retire(store.read().roles.get(role_id, RoleVoice()))
            result = store.save_role(role_id, voice.model_dump())
            references.imported.difference_update(
                ref.asset for ref in [voice.default, *voice.moods.values()] if ref
            )
            references.collect()
            return result.model_dump()

    async def import_reference(params: dict[str, object]):
        with ctx.roles.read_scope():
            require_role(params)
            return references.import_file(ctx.workspace, str(params.get("source", "")))

    for name, handler in [
        ("settings.get", get),
        ("health", health),
        ("role.get", role_get),
    ]:
        ctx.rpc.register(name, handler, concurrency=Concurrency.READ_ONLY)
    for name, handler in [
        ("settings.set", save),
        ("role.set", role_save),
        ("reference.import", import_reference),
    ]:
        ctx.rpc.register(name, handler)
    ctx.rpc.register("reconnect", engine.reconnect, concurrency=Concurrency.INTEGRATION)
