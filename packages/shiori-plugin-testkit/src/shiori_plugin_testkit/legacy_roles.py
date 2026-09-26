"""Seed historical role manifests for migration and channel compatibility tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.roles.manifest import RoleManifestRepository
from core.roles.models import RoleChannelBindingConfig, RoleRecord


def seed_legacy_bindings(
    workspace: Path, role_id: str, bindings: list[dict[str, Any]]
) -> RoleRecord:
    """Write pre-account bindings to a test workspace's role manifest."""
    repository = RoleManifestRepository(workspace)
    roles = repository.list_roles()
    role = next((item for item in roles if item.id == role_id), None)
    if role is None:
        raise KeyError(role_id)
    role.channel_bindings = [
        RoleChannelBindingConfig.from_dict(item) for item in bindings
    ]
    repository.save_roles(roles)
    return role
