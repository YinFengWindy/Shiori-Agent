"""The ``resources`` plugin capability: host-distributed resources (#901 P2).

``HostResources`` is the ``host.resources`` core service, one per kernel
generation and shared by every plugin; it resolves the resource root of source
and frozen installations. It satisfies ``shiori_sdk.processes.Resources``.
"""

from pathlib import Path

from bootstrap.paths import common_emojis_paths, resource_root


class HostResources:
    """Resolve host-distributed resources in source and frozen installations."""

    @property
    def root(self) -> Path:
        """Return the configured host resource root."""
        return resource_root()

    def common_emojis(self, workspace: Path) -> tuple[Path, ...]:
        """Return user overrides followed by the packaged emoji resource."""
        return tuple(common_emojis_paths(workspace))
