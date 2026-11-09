"""Reconcile desktop intent without interpreting provider assets."""

from pathlib import Path
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.roles import Roles
from .models import RolePetState
from .storage import PLUGIN_ID


class PetStateReconciler:
    """Remove deleted roles; preserve selections during provider absence."""

    def __init__(self, roles: Roles, workspace: Path) -> None:
        self._roles = roles

    def reconcile(self) -> None:
        """Retain at most one enabled role without dropping unavailable models."""
        with self._roles.read_scope():
            roles = self._roles.list_roles()
            ids = {role.id for role in roles}

            def prune(data):
                for role_id in list(data):
                    if role_id not in ids:
                        del data[role_id]
                enabled = False
                for role in roles:
                    if role.id not in data:
                        continue
                    state = RolePetState.from_dict(role.id, data[role.id])
                    state.desktop_pet_enabled = (
                        state.desktop_pet_enabled and not enabled
                    )
                    enabled = enabled or state.desktop_pet_enabled
                    data[role.id] = {
                        **data[role.id],
                        "desktop_pet_enabled": state.desktop_pet_enabled,
                    }

            self._roles.extensions.update(PLUGIN_ID, prune)

    async def on_role_deleted(self, _event: RoleDeleted) -> None:
        """Apply the same cleanup after live role deletion."""
        self.reconcile()
