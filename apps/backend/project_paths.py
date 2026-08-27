"""Filesystem roots shared by backend code that reaches outside the application."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
