"""Independent 2.5D provider registration using the desktop model contract."""

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
from shiori_sdk.rpc import Concurrency
from shiori_sdk.runtime import PluginRuntimeContext
from plugins.desktop_pet.backend.api import PET_MODELS_CONTRACT, PetProvidersAPI
from plugins.desktop_pet.backend.provider_presentation import ProviderPresentation

from .provider import AvatarModels
from .storage import reconcile


async def setup(ctx: PluginRuntimeContext) -> None:
    """Publish models after cleanup, and retire registrations with their owning scope."""
    desktop = ctx.require(DEPENDENCIES).require("desktop_pet")
    if not isinstance(desktop, PetProvidersAPI):
        raise TypeError("desktop_pet dependency must export PetProvidersAPI")
    roles, workspace = ctx.require(ROLES), ctx.require(WORKSPACE)
    reconcile(roles, workspace)

    async def on_deleted(_event: RoleDeleted) -> None:
        reconcile(roles, workspace)

    ctx.require(EVENTS).on(RoleDeleted, on_deleted)
    models = AvatarModels(roles, workspace)
    ctx.effect("pet_2d_provider", desktop.register(models))
    presentation = ProviderPresentation(
        ctx.require(RPC), models.presentation, label="2.5D"
    )
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
