"""``on`` chain verdicts, failure policies, core checks and ``watch`` delivery."""

import asyncio
import dataclasses
import logging
from dataclasses import dataclass
from typing import ClassVar

import pytest

from shiori_sdk.kernel import FailurePolicy, Scope, Veto
from shiori_sdk.kernel.events import EventHub


@dataclass(frozen=True)
class Calling:
    command: str


@dataclass(frozen=True)
class Guarded:
    on_error: ClassVar[FailurePolicy] = "fail_closed"
    command: str


@dataclass
class Mutable:
    value: int


@dataclass(frozen=True)
class Listed:
    items: list[str]


def hub(*ranked: str, limit: int = 256) -> EventHub:
    return EventHub(lambda plugin_id: ranked.index(plugin_id), limit)


async def settle(events: EventHub) -> None:
    """Waits for every watch worker (what ``KernelHarness.idle`` does)."""
    for queue in list(events._queues.values()):  # pyright: ignore[reportPrivateUsage]
        if queue.worker is not None:
            _ = await asyncio.gather(queue.worker, return_exceptions=True)


async def test_on_chain_follows_rank_not_registration_time() -> None:
    events = hub("first", "second")
    seen: list[str] = []

    def append(name: str):
        async def handler(event: Calling) -> Calling:
            seen.append(name)
            return Calling(f"{event.command}+{name}")

        return handler

    events.on("second", Scope("second"), Calling, append("second"))
    events.on("first", Scope("first"), Calling, append("first:a"))
    events.on("first", Scope("first"), Calling, append("first:b"))

    assert await events.emit(Calling("ls")) == Calling("ls+first:a+first:b+second")
    assert seen == ["first:a", "first:b", "second"]


async def test_veto_stops_the_chain_and_skips_checks_and_watchers() -> None:
    events = hub("guard", "later")
    reached: list[str] = []

    async def veto(event: Calling) -> Veto:
        return Veto("blocked")

    async def later(event: Calling) -> Calling:
        reached.append("later")
        return event

    async def watcher(event: Calling) -> None:
        reached.append("watcher")

    async def check(event: Calling) -> Calling:
        reached.append("check")
        return event

    events.on("guard", Scope("guard"), Calling, veto)
    events.on("later", Scope("later"), Calling, later)
    events.watch("later", Scope("later"), Calling, watcher)
    events.check(Calling, check)

    assert await events.emit(Calling("rm")) == Veto("blocked")
    await settle(events)
    assert reached == []


async def test_returning_none_is_a_handler_error_not_a_deletion() -> None:
    events = hub("silent")

    async def silent(event: Guarded) -> None:
        return None

    events.on("silent", Scope("silent"), Guarded, silent)  # type: ignore[arg-type]

    verdict = await events.emit(Guarded("ls"))

    assert isinstance(verdict, Veto)
    assert "silent" in verdict.reason


async def test_fail_open_logs_the_error_and_passes_the_event_on(caplog) -> None:
    events = hub("broken", "next")

    async def broken(event: Calling) -> Calling:
        raise RuntimeError("boom")

    async def suffix(event: Calling) -> Calling:
        return Calling(event.command + "!")

    events.on("broken", Scope("broken"), Calling, broken)
    events.on("next", Scope("next"), Calling, suffix)

    with caplog.at_level(logging.ERROR, "shiori.plugin.broken"):
        assert await events.emit(Calling("ls")) == Calling("ls!")
    assert [r.name for r in caplog.records] == ["shiori.plugin.broken"]


async def test_fail_closed_handler_error_aborts_the_chain_with_a_veto() -> None:
    events = hub("broken", "next")
    reached: list[str] = []

    async def broken(event: Guarded) -> Guarded:
        raise RuntimeError("boom")

    async def after(event: Guarded) -> Guarded:
        reached.append("next")
        return event

    events.on("broken", Scope("broken"), Guarded, broken)
    events.on("next", Scope("next"), Guarded, after)

    verdict = await events.emit(Guarded("rm -rf /"))

    assert verdict == Veto("插件 broken 处理 Guarded 失败: boom")
    assert reached == []


async def test_core_check_runs_on_the_final_event_after_plugin_rewrites() -> None:
    events = hub("rewriter")

    async def rewrite(event: Calling) -> Calling:
        return Calling("rm -rf /")

    async def minimal_shell_guard(event: Calling) -> Calling | Veto:
        return Veto("dangerous") if "rm -rf" in event.command else event

    events.on("rewriter", Scope("rewriter"), Calling, rewrite)
    events.check(Calling, minimal_shell_guard)

    assert await events.emit(Calling("ls")) == Veto("dangerous")


async def test_emit_does_not_wait_for_watchers_and_their_errors_stay_out() -> None:
    events = hub("observer")
    release = asyncio.Event()
    seen: list[Calling] = []

    async def slow(event: Calling) -> None:
        await release.wait()
        seen.append(event)
        raise RuntimeError("watcher failed")

    events.watch("observer", Scope("observer"), Calling, slow)

    assert await events.emit(Calling("ls")) == Calling("ls")
    assert seen == []
    release.set()
    await settle(events)
    assert seen == [Calling("ls")]


async def test_watch_delivers_serially_per_plugin_and_event_type() -> None:
    events = hub("observer")
    running = 0
    peak = 0
    seen: list[str] = []

    async def record(event: Calling) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0)
        seen.append(event.command)
        running -= 1

    events.watch("observer", Scope("observer"), Calling, record)
    for command in ("a", "b", "c"):
        _ = await events.emit(Calling(command))
    await settle(events)

    assert seen == ["a", "b", "c"]
    assert peak == 1


async def test_watch_queue_overflow_drops_counts_and_logs(caplog) -> None:
    events = hub("observer", limit=2)
    release = asyncio.Event()
    seen: list[str] = []

    async def record(event: Calling) -> None:
        await release.wait()
        seen.append(event.command)

    events.watch("observer", Scope("observer"), Calling, record)
    with caplog.at_level(logging.WARNING, "shiori.plugin.observer"):
        for command in ("a", "b", "c", "d"):
            _ = await events.emit(Calling(command))
            await asyncio.sleep(0)
    release.set()
    await settle(events)

    # "a" was taken by the worker at once; "b" and "c" filled the queue.
    assert seen == ["a", "b", "c"]
    # Counted and logged through the plugin's own logger (``ctx.log``).
    dropped = [r for r in caplog.records if "累计" in r.getMessage()]
    assert [r.name for r in dropped] == ["shiori.plugin.observer"]
    assert dropped[0].getMessage().endswith("（累计 1）")


async def test_watcher_cannot_change_the_frozen_event() -> None:
    events = hub("observer", "other")
    errors: list[BaseException] = []
    seen: list[Calling] = []

    async def tamper(event: Calling) -> None:
        try:
            event.command = "rm -rf /"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError as error:
            errors.append(error)

    async def record(event: Calling) -> None:
        seen.append(event)

    events.watch("observer", Scope("observer"), Calling, tamper)
    events.watch("other", Scope("other"), Calling, record)
    _ = await events.emit(Calling("ls"))
    await settle(events)

    assert len(errors) == 1
    assert seen == [Calling("ls")]
    with pytest.raises(TypeError, match="frozen"):
        events.watch("observer", Scope("observer"), Mutable, tamper)  # type: ignore[arg-type]


async def test_watched_event_with_a_mutable_container_field_is_rejected() -> None:
    events = hub("observer")
    seen: list[Listed] = []

    async def record(event: Listed) -> None:
        seen.append(event)

    events.watch("observer", Scope("observer"), Listed, record)

    with pytest.raises(TypeError, match="tuple"):
        _ = await events.emit(Listed(["a"]))
    await settle(events)
    assert seen == []
