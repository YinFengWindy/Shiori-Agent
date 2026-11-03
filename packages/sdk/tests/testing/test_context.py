"""Contract fakes exercise setup, declared keys and cleanup without host storage."""

import pytest

from shiori_sdk.core.services import HTTP, KV, RPC
from shiori_sdk.kernel import KernelError
from shiori_sdk.testing import FakePluginContext
from shiori_sdk.testing.memory_context import FakeRpc
from shiori_sdk.testing.storage import FakeKV


async def test_cleanup_is_lifo_stops_events_first_and_rejects_cached_registrations() -> (
    None
):
    context = FakePluginContext()
    events = context.fake_events
    seen: list[str] = []

    def handler(event: str) -> None:
        seen.append(event)

    events.on(str, handler)
    context.effect("first", lambda: seen.append("first"))

    async def close() -> None:
        await events.emit("must not be delivered")
        seen.append("second")

    context.effect("second", close)
    await context.aclose()
    assert seen == ["second", "first"]
    with pytest.raises(RuntimeError, match="closed"):
        events.on(str, handler)
    with pytest.raises(RuntimeError, match="closed"):
        context.effect("late", lambda: None)
    await context.aclose()
    assert seen == ["second", "first"]


async def test_cleanup_continues_after_a_failure() -> None:
    context = FakePluginContext()
    seen: list[str] = []
    context.effect("first", lambda: seen.append("first"))

    def fail() -> None:
        raise ValueError("cleanup failed")

    context.effect("failure", fail)
    with pytest.raises(ExceptionGroup, match="Plugin cleanup failed"):
        await context.aclose()
    assert seen == ["first"]


def test_require_and_get_reject_undeclared_keys_like_the_host() -> None:
    context = FakePluginContext(inject=("kv",), optional_inject=("http",))
    kv, rpc = FakeKV(), FakeRpc()
    context.serve(KV, kv)
    context.serve(RPC, rpc)
    assert context.require(KV) is kv
    assert context.get(HTTP) is None
    # A served fake never stands in for a key the declaration lacks.
    for lookup in (lambda: context.require(RPC), lambda: context.get(RPC)):
        with pytest.raises(KernelError) as caught:
            lookup()
        assert caught.value.diagnostic.code == "undeclared_key"


def test_removed_capability_attributes_can_be_neither_set_nor_read() -> None:
    """The host context has no ``ctx.kv``; a plugin reading it must fail here too."""
    context = FakePluginContext(inject=("kv",))
    with pytest.raises(AttributeError, match="ctx.require"):
        context.kv = FakeKV()  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError, match="ctx.require"):
        _ = context.rpc  # pyright: ignore[reportAttributeAccessIssue]
