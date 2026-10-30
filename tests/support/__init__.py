"""Host-only test support; never installed in the plugin testkit.

Three stacks, three jobs:

- ``shiori_sdk.testing`` — fakes for plugin tests. No host import.
- ``shiori_host_testing`` — real ``AppRuntime`` (``plugin_runtime``) and a
  workspace-backed ``FakeMemoryEngine``. Host development only.
- ``tests.support`` — host scenario builders (plugin kernel, the
  real external-turn loop in ``host_external_turns``). Not the SDK fake
  ``shiori_sdk.testing.external_turns.FakeExternalTurns``.
"""
