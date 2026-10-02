"""Host-independent public contracts for Shiori plugins."""

from ._version import RUNTIME_API_VERSION, __version__
from .runtime import (
    CapabilityNotGranted,
    HostServiceUnavailable,
    PluginRuntimeContext,
)
