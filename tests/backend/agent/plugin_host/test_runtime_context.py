"""The v2 setup context's kernel members: manifest keys and the generation's events."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.core.turn_events import TurnEvents
from bus.event_bus import EventBus
from shiori_sdk.core.conversation import ReasoningStarting
from shiori_sdk.kernel import Key
from tests.support.plugin_kernel import make_kernel

_PLUGIN = """
from dataclasses import replace

from shiori_sdk.core.conversation import ReasoningStarting
from shiori_sdk.core.crash_reporting import CRASH_REPORTING
from shiori_sdk.kernel import Key

API = object()
crash_reporting = []


async def setup(ctx):
    crash_reporting.append(ctx.require(CRASH_REPORTING))
    ctx.provide(Key("keyed.api"), API)
    ctx.on(ReasoningStarting, _hint)


async def _hint(event):
    return replace(event, extra_hints=(*event.extra_hints, "keyed"))
""".strip()

_MANIFEST = (
    "api: 2\nid: keyed\nversion: '0.1'\ncapabilities: []\n"
    "inject:\n  - crash_reporting\nprovides:\n  - keyed.api\n"
)


def _starting() -> ReasoningStarting:
    return ReasoningStarting(
        session_key="role:mira",
        channel="desktop",
        chat_id="mira",
        content="hello",
        timestamp=datetime.now(timezone.utc),
    )


async def test_manifest_keys_and_events_go_through_the_generation_kernel(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "keyed"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(_PLUGIN, encoding="utf-8")
    (plugin_dir / "manifest.yaml").write_text(_MANIFEST, encoding="utf-8")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    events = TurnEvents(EventBus(), lambda: kernel.kernel)
    hints: list[tuple[str, ...]] = []

    def apply(event: ReasoningStarting) -> None:
        hints.append(event.extra_hints)

    try:
        module = next(
            m
            for k, m in sys.modules.items()
            if k.startswith("akasic_plugin_") and k.endswith("_keyed")
        )
        assert module.crash_reporting[0] is not None
        assert kernel.kernel.get(Key("keyed.api")) is module.API
        await events.emit(_starting(), apply)
        _ = await kernel.unload("keyed")
        await events.emit(_starting(), apply)
    finally:
        await kernel.terminate_all(force=True)

    assert hints == [("keyed",), ()]
    assert kernel.kernel.get(Key("keyed.api")) is None
