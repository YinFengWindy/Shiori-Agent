"""Renderer peer versions the host guarantees to external packages."""

from __future__ import annotations

from dataclasses import dataclass, field

# This is the renderer ABI's guaranteed minimum, not a probe of the developer's npm tree.
REACT_API_VERSION = "19.2.0"


@dataclass(frozen=True)
class HostRuntimeContract:
    """Host React versions that compiled frontend peer metadata must admit."""

    renderer_peers: dict[str, str] = field(
        default_factory=lambda: {
            "react": REACT_API_VERSION,
            "react-dom": REACT_API_VERSION,
        }
    )
