"""Independent plugin test doubles. No host database or AppRuntime is created.

Host integration fixtures live in ``shiori_host_testing`` (not published with
the SDK). Host scenario builders live in the repository's ``tests.support``
and are not importable from an installed plugin.
"""

from .context import FakePluginContext
from .events import FakeEvents
from .lifecycle import FakeFrame, FakeLifecycle
