"""Filesystem roots shared by backend code that reaches outside the application."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]

# Canonical template copied into user-owned workspace configurations during setup.
CONFIG_TEMPLATE_PATH = BACKEND_ROOT / "config.example.toml"
