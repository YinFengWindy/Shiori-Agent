"""Provider-owned sprite metadata; selection belongs to desktop_pet."""

from dataclasses import dataclass, field
from typing import Any
from shiori_sdk.roles import Roles
from .models import RolePetPackage
from .storage import PLUGIN_ID


@dataclass
class RoleSpriteState:
    """The sprite models installed for one role."""

    id: str
    pet_packages: list[RolePetPackage] = field(default_factory=list)


class RolePetStateStore:
    """Owns sprite metadata only, never the role's presentation switch."""

    def __init__(self, roles: Roles) -> None:
        self.roles = roles

    def get_role(self, role_id: str) -> RoleSpriteState | None:
        """Read validated metadata for an existing role."""
        with self.roles.read_scope():
            if self.roles.get_role(role_id) is None:
                return None
            raw: Any = self.roles.extensions.read(PLUGIN_ID).get(role_id, {})
            return RoleSpriteState(
                role_id, [RolePetPackage.from_dict(p) for p in raw.get("packages", [])]
            )

    def require_role(self, role_id: str) -> RoleSpriteState:
        """Reject unknown roles before asset operations."""
        role = self.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        return role

    def replace_packages(self, role_id: str, packages: list[RolePetPackage]) -> None:
        """Publish metadata without changing another plugin's role state."""
        with self.roles.read_scope():
            self.require_role(role_id)

            def publish(data: dict[str, Any]) -> None:
                data[role_id] = {
                    **data.get(role_id, {}),
                    "packages": [p.to_dict() for p in packages],
                }

            self.roles.extensions.update(PLUGIN_ID, publish)
