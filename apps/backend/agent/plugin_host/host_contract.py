"""Host-owned dependency inventory; validation never imports plugin dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import metadata

RUNTIME_API_VERSION = "2.1.0"
# This is the renderer ABI's guaranteed minimum, not a probe of the developer's npm tree.
REACT_API_VERSION = "19.2.0"


def _distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def installed_host_dependencies() -> frozenset[str]:
    """Expose installed direct production requirements, excluding dev/transitive APIs.

    Distribution metadata is read without importing any package. Frozen hosts must
    supply their build inventory explicitly when distribution metadata is absent.
    """
    try:
        requirements = metadata.requires("shiori-agent") or []
    except metadata.PackageNotFoundError:
        return frozenset()
    names: set[str] = set()
    for requirement in requirements:
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
        if match is None or ";" in requirement:
            continue
        name = _distribution_name(match[0])
        # A bundled plugin distribution is not part of the public dependency API.
        if name.startswith("shiori-plugin-"):
            continue
        try:
            _ = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        names.add(name)
    return frozenset(names)


@dataclass(frozen=True)
class HostRuntimeContract:
    """Advertised API guarantees and installed dependency names for this host build."""

    runtime_api: str = RUNTIME_API_VERSION
    python_dependencies: frozenset[str] = field(
        default_factory=installed_host_dependencies
    )
    renderer_peers: dict[str, str] = field(
        default_factory=lambda: {
            "react": REACT_API_VERSION,
            "react-dom": REACT_API_VERSION,
        }
    )

    def provides_python(self, name: str) -> bool:
        """Match a declared distribution using Python's normalized distribution name."""
        return _distribution_name(name) in self.python_dependencies
