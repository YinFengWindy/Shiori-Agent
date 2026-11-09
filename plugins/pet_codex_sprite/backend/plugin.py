"""Independent Codex sprite provider, depending only on desktop_pet's API."""

from functools import partial
from shiori_sdk.core.services import (
    DEPENDENCIES,
    EVENTS,
    ROLES,
    RPC,
    SERVICES,
    WORKSPACE,
)
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.runtime import PluginRuntimeContext
from shiori_sdk.rpc import Concurrency
from plugins.desktop_pet.backend.api import PET_MODELS_CONTRACT, PetProvidersAPI
from .provider import SpriteModels
from .presentation import SpritePresentation
from .reconcile import SpriteReconciler


async def setup(ctx: PluginRuntimeContext) -> None:
    """Migrate assets before publishing the provider and its model service."""
    desktop = ctx.require(DEPENDENCIES).require("desktop_pet")
    if not isinstance(desktop, PetProvidersAPI):
        raise TypeError("desktop_pet dependency must export PetProvidersAPI")
    roles, workspace = ctx.require(ROLES), ctx.require(WORKSPACE)
    reconciler = SpriteReconciler(roles, workspace, desktop)
    reconciler.reconcile()
    ctx.require(EVENTS).on(RoleDeleted, reconciler.on_role_deleted)
    models = SpriteModels(roles, workspace)
    ctx.effect("sprite_provider", desktop.register(models))
    presentation = SpritePresentation(models, ctx.require(RPC))
    ctx.require(RPC).register(
        "presentation.ready",
        presentation.set_ready,
        concurrency=Concurrency.MUTATION,
        admission_exempt=True,
    )

    async def model_call(method: str, payload: dict[str, object]) -> dict[str, object]:
        role_id = payload.get("role_id")
        if not isinstance(role_id, str) or not role_id.strip():
            raise ValueError("缺少 role_id")
        if method == "list":
            return {"models": models.list_models(role_id)}
        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("缺少 model_id")
        return {"model": models.get_model(role_id, model_id)}

    ctx.require(SERVICES).register(
        "models",
        contract=PET_MODELS_CONTRACT,
        label=models.label,
        methods={
            "list": partial(model_call, "list"),
            "get": partial(model_call, "get"),
            "present": presentation.present,
        },
        metadata={"import": models.import_options},
    )
