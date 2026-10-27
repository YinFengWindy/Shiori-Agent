"""``MEMORY_ENGINE``: the memory engine socket (D1).

The host does not construct an engine. A plugin that declares
``provides: [memory_engine]`` builds one in ``setup`` and ``provide``s it.
Consumers declare ``optional_inject: [memory_engine]`` and ``get`` it on every
use. ``None`` means this generation has no engine: retrieval is skipped and
chat still runs.
"""

from __future__ import annotations

from shiori_sdk.kernel import Key
from shiori_sdk.memory.engine import MemoryEngine

MEMORY_ENGINE: Key[MemoryEngine] = Key("memory_engine")
"""The engine socket. Plugins provide it; the host never does."""
