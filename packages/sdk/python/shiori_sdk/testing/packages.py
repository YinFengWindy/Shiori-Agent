"""Location of explicitly available plugin packages, without repository assumptions."""

from importlib.util import find_spec
from pathlib import Path
import shutil


def plugin_directory(plugin_id: str) -> Path:
    """Returns the installed/imported plugin package owning its manifest and backend."""
    spec = find_spec(f"plugins.{plugin_id}")
    if spec is None or not spec.submodule_search_locations:
        raise ModuleNotFoundError(f"Plugin dependency is not installed: {plugin_id}")
    return Path(next(iter(spec.submodule_search_locations))).resolve()


def stage_plugin_package(source: Path, target: Path) -> Path:
    """Copies a plugin and its tests without development environments or local state.

    Virtual environments are recognized by .venv or a directory's pyvenv.cfg.
    Build outputs and plugin state are excluded only at their owning package paths;
    similarly named resource directories and fixture files remain available.
    """
    source = source.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        ignored: set[str] = set()
        for name in names:
            child = current / name
            if child.is_dir():
                if (
                    name
                    in {
                        ".venv",
                        "__pycache__",
                        ".pytest_cache",
                        ".ruff_cache",
                        ".mypy_cache",
                        "node_modules",
                    }
                    or name.endswith(".egg-info")
                    or (child / "pyvenv.cfg").is_file()
                ):
                    ignored.add(name)
                elif current == source and name in {"build", "dist", ".git", ".data"}:
                    ignored.add(name)
            elif name.endswith((".pyc", ".pyo")):
                ignored.add(name)
            if current == source and name in {
                ".git",
                ".kv.json",
                "plugin.disabled",
                "plugin_config.json",
                "config.local.toml",
            }:
                ignored.add(name)
            if current == source / "backend" and name == "config.local.toml":
                ignored.add(name)
        return ignored

    return Path(shutil.copytree(source, target, ignore=ignore))
