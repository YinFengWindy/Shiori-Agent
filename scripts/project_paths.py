"""Shared repository locations for standalone maintenance scripts."""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPOSITORY_ROOT / "apps" / "backend"


def add_backend_to_sys_path() -> None:
    """Make backend top-level packages importable for a standalone script."""
    backend_root = str(BACKEND_ROOT)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
