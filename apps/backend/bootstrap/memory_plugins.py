"""Load independent memory engines from their owning plugin packages."""

from __future__ import annotations

import hashlib
import importlib
from importlib.machinery import ModuleSpec
from importlib.util import module_from_spec
import re
import sys
from types import ModuleType

from bootstrap.paths import plugin_roots


def normalize_memory_engine(name: str) -> str:
    """Normalize the default selector and reject paths or invalid package names."""
    normalized = (name or "default").strip() or "default"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", normalized) is None:
        raise ValueError(f"memory engine 名称非法: {name}")
    return normalized


def load_memory_plugin_module(name: str, module: str) -> ModuleType:
    """Import a memory backend module with stable identity across host callers.

    Source, wheel and frozen runs all use the owning resource roots. The private
    package stays independent of ordinary plugin generations and their unloads.
    """
    engine = normalize_memory_engine(name)
    package = "default_memory" if engine == "default" else engine
    backend = next(
        (
            root / package / "backend"
            for root in plugin_roots()
            if (root / package / "backend" / "memory_plugin.py").is_file()
        ),
        None,
    )
    if backend is None:
        raise ValueError(
            f"未知 memory engine: {engine}；可选值: default 或已安装的记忆引擎插件"
        )
    backend = backend.resolve()
    # Include the owning directory so separate installations never share classes
    # or configuration, while repeated builds reuse this package's module graph.
    digest = hashlib.sha256(str(backend).encode("utf-8")).hexdigest()
    namespace = f"_shiori_memory_{package}_{digest}"
    if namespace not in sys.modules:
        spec = ModuleSpec(namespace, loader=None, is_package=True)
        spec.submodule_search_locations = [str(backend)]
        sys.modules[namespace] = module_from_spec(spec)
    return importlib.import_module(f"{namespace}.{module}")
