"""Codex provider policy for native-selected ZIP imports."""

from pathlib import Path
from plugins.desktop_pet.backend.provider_files import resolve_staged_zip


def resolve_package_import_source(workspace: Path, source: str) -> Path:
    """Require the sprite provider's native namespace and 32 MB package limit."""
    return resolve_staged_zip(
        workspace, source, namespace="pet_codex_sprite-pets", max_bytes=32 * 1024 * 1024
    )
