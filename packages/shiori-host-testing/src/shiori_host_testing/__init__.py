"""Host-owned integration fixtures; never installed with the SDK.

``plugin_runtime`` starts a real ``AppRuntime``. ``FakeMemoryEngine`` is backed
by the host memory store when a workspace is supplied. Plugin tests use
``shiori_sdk.testing`` instead, and must not import this package.
"""
