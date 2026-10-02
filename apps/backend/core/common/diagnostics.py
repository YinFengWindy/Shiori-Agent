"""Runtime diagnostic attribution with explicit installed-code roots."""

import traceback
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from importlib.util import find_spec
from core.error_context import current_session_key
from core.common import global_hook_stack


class HostDiagnostics:
    """Own global hook dispatch and identify host or external-plugin traceback frames."""

    def __init__(self, plugin_roots: Sequence[tuple[str, Path]] = ()) -> None:
        self._roots = list(plugin_roots)
        # Package locations remain valid in a source tree, wheel or frozen layout.
        for name in (
            "agent",
            "bootstrap",
            "bus",
            "conversation",
            "core",
            "desktop_bridge",
            "infra",
            "proactive_v2",
            "prompts",
            "session",
            "utils",
            "shiori_runtime_resources",
        ):
            spec = find_spec(name)
            if spec is not None and spec.submodule_search_locations is not None:
                self._roots.extend(
                    (name, Path(path).resolve())
                    for path in spec.submodule_search_locations
                )

    def session_key(self) -> str | None:
        """Read the host's current passive-turn error attribution."""
        return current_session_key.get()

    def top_frame(self, tb: TracebackType | None) -> str:
        """Prefer the first owned frame; otherwise report the innermost filename."""
        frames = traceback.extract_tb(tb) if tb else []
        for frame in frames:
            for label, root in self._roots:
                path = Path(frame.filename).resolve()
                if path.is_relative_to(root):
                    return f"{label}/{path.relative_to(root).as_posix()}:{frame.lineno or 0}"
        return (
            f"{Path(frames[-1].filename).name}:{frames[-1].lineno or 0}"
            if frames
            else "?"
        )

    install_global_hooks = staticmethod(global_hook_stack.install_global_hooks)
    uninstall_global_hooks = staticmethod(global_hook_stack.uninstall_global_hooks)
