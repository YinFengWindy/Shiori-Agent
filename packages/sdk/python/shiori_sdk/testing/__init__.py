"""Independent plugin test doubles. No host database or AppRuntime is created."""

from .context import FakePluginContext
from .events import FakeEvents
from .lifecycle import FakeFrame, FakeLifecycle
