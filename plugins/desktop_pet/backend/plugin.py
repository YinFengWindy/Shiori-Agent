from __future__ import annotations

from typing import TYPE_CHECKING


from .rpc import DesktopPetRpcHandlers
from .tool import DesktopPetActionTool
if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Registers pet-owned data, explicit role-save participation and RPCs."""
    from desktop_bridge.method_policy import Concurrency
    from bus.events_lifecycle import RoleDeleted

    # Prepared and active runtimes share RoleStore; use the same stateless
    # callback identities even though plugin.py is imported per generation.
    from .pet_state import PLUGIN_ID, RolePetStateStore
    from .reconcile import PetStateReconciler

    role_store = ctx.role_store
    if role_store is None:
        raise RuntimeError("桌宠插件需要 role_store")
    reconciler = PetStateReconciler(role_store)
    reconciler.reconcile()
    ctx.effect(
        "role_settings",
        role_store.extensions.register(
            PLUGIN_ID, RolePetStateStore.write_draft, RolePetStateStore.project
        ),
    )
    ctx.events.on(RoleDeleted, reconciler.on_role_deleted)
    ctx.tools.register(
        DesktopPetActionTool(
            role_store=role_store,
            event_bus=ctx.events,
            tool_registry=ctx.tools,
        ),
        risk="external-side-effect",
        always_on=True,
        search_hint="桌宠 移动 位置 动作 挥手 跳跃",
    )
    handlers = DesktopPetRpcHandlers(role_store=role_store)
    ctx.rpc.register(
        "binding.get", handlers.binding_get, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register("pets.list", handlers.pets_list, concurrency=Concurrency.READ_ONLY)
    # 三个写方法用默认的 Concurrency.MUTATION，与它们此前作为 roles.pets.*
    # 走 _DEFAULT_POLICY 时的并发语义一致。
    ctx.rpc.register("pets.import", handlers.pets_import)
    ctx.rpc.register("pets.remove", handlers.pets_remove)
    ctx.rpc.register("pets.select", handlers.pets_select)
