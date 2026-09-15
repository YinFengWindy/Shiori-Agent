"""Source-only import boundary for one trusted external plugin namespace."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder, SourceFileLoader
from pathlib import Path
from types import CodeType, ModuleType


class _VerifiedSourceLoader(SourceFileLoader):
    def __init__(self, name: str, path: str, source: bytes) -> None:
        super().__init__(name, path)
        self._source = source

    def get_code(self, fullname: str) -> CodeType:
        # Never read or write bytecode caches, even when a valid-looking pyc exists.
        return self.source_to_code(self._source, self.path)


class TrustedPluginImports(MetaPathFinder):
    """Loads only verified Python bytes; lazy relative imports share the same snapshot."""

    def __init__(self, namespace: str, sources: dict[str, bytes]) -> None:
        self._namespace = namespace
        self._sources = sources

    def loader(self, name: str, path: Path) -> SourceFileLoader:
        """Build a source loader from the verified snapshot, rejecting new modules."""
        canonical = str(path.resolve())
        source = self._sources.get(canonical)
        if source is None:
            raise ImportError("插件源码不在已信任内容中，请重启并重新确认信任")
        return _VerifiedSourceLoader(name, str(path), source)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        """Intercept only this plugin's relative imports, leaving the host untouched."""
        if not fullname.startswith(self._namespace + "."):
            return None
        spec = PathFinder.find_spec(fullname, path)
        if spec is None:
            raise ModuleNotFoundError(f"插件模块 {fullname} 不在已信任源码中")
        if spec.origin is not None:
            spec.loader = self.loader(fullname, Path(spec.origin))
        return spec

    def install(self) -> None:
        """Install this namespace boundary for the owning plugin lifetime."""
        sys.meta_path.insert(0, self)

    def remove(self) -> None:
        """Release the finder with the plugin's other scoped effects."""
        if self in sys.meta_path:
            sys.meta_path.remove(self)
