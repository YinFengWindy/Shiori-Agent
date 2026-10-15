import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures
from shiori_sdk.messages import OutboundMessage
from core.common.runtime_scope import bind_runtime, current_runtime_lease

# 渠道插件：token 即账号，换 token 就是换账号；Transport 由测试注入，便于记录发送。
_TRANSPORT_MODULE = "_channel_barrier_transport"
_PLUGIN_PY = f"""
import sys


async def setup(ctx):
    token = ctx.config.as_dict().get("token")
    if token:
        ctx.channels.add(sys.modules["{_TRANSPORT_MODULE}"].Transport(token=token))
""".strip()


def _config(account: str) -> dict[str, dict[str, object]]:
    return {"barrier": {"token": account}}


def _install_transport(monkeypatch, sent, tmp_path: Path):
    class Transport:
        name = "fake"

        def __init__(self, *, token):
            self.token = token
            self.running = False
            self.paused = False

        async def start(self, context):
            self.context = context
            self.running = True
            self.paused = getattr(context, "intake_paused", False)
            context.bus.subscribe_outbound(self.name, self.send_outbound)

        async def stop(self):
            self.running = False
            self.context.bus.unsubscribe_outbound(self.name, self.send_outbound)

        async def send(self, chat_id, text):
            assert self.running
            sent.append((self.token, text))

        async def send_outbound(self, message):
            await self.send(message.chat_id, message.content)

        def pause_intake(self):
            self.paused = True

        def resume_intake(self):
            self.paused = False

    module = ModuleType(_TRANSPORT_MODULE)
    module.Transport = Transport
    monkeypatch.setitem(sys.modules, _TRANSPORT_MODULE, module)
    root = tmp_path / "plugin_dirs"
    package = root / "barrier"
    (package / "backend").mkdir(parents=True)
    (package / "backend" / "plugin.py").write_text(_PLUGIN_PY, encoding="utf-8")
    (package / "manifest.yaml").write_text(
        "api: 2\nid: barrier\ncapabilities: [config, channels]\nchannels:\n"
        "  - {name: fake, label: Fake,"
        " chat_types: [{type: private, label: 私聊, chat_id_label: ID}]}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])


def _install_background_work(monkeypatch):
    loops = []

    class BackgroundWork:
        def __init__(self):
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()
            self.stop_calls = 0

        async def run(self):
            if self.stopped.is_set():
                return
            self.started.set()
            await self.stopped.wait()

        def stop(self):
            self.stop_calls += 1
            self.stopped.set()

    def build(*args, loop_consumer, **kwargs):
        loop = BackgroundWork()
        loops.append(loop)
        loop_consumer(loop)
        return [loop.run()], None

    monkeypatch.setattr(
        "bootstrap.runtime.background.build_memory_optimizer_task", build
    )
    return loops


async def _prepare_account_switch(tmp_path, monkeypatch):
    _install_transport(monkeypatch, [], tmp_path)
    loops = _install_background_work(monkeypatch)
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        plugins=_config("account-A"),
    )
    app = AppRuntime(config, tmp_path, features=RuntimeFeatures(enable_proactive=False))
    await app.start()
    await asyncio.wait_for(loops[0].started.wait(), 1)
    candidate = await app.prepare(replace(config, plugins=_config("account-B")))
    return app, candidate, loops


@pytest.mark.asyncio
async def test_credential_change_drains_old_queued_replies_before_switch(
    tmp_path, monkeypatch
):
    sent = []
    _install_transport(monkeypatch, sent, tmp_path)
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        plugins=_config("account-A"),
    )
    app = AppRuntime(config, tmp_path, features=RuntimeFeatures(enable_proactive=False))
    await app.start()
    accepted = app.acquire()
    candidate = await app.prepare(replace(config, plugins=_config("account-B")))
    publish = asyncio.create_task(app.publish(candidate))
    try:
        for _ in range(10):
            if not app._generation_manager.admission.is_set():
                break
            await asyncio.sleep(0)
        assert not app._generation_manager.admission.is_set()
        assert not app.accepting_work
        assert not publish.done()
        with bind_runtime(accepted):
            await accepted.core.bus.publish_outbound(
                OutboundMessage("fake", "chat", "queued old")
            )
        await accepted.release()
        await asyncio.wait_for(publish, 3)
        assert sent == [("account-A", "queued old")]
        assert app.generation == 2
        assert app._generation_manager.admission.is_set()
        assert app.accepting_work
        async with app.acquire() as fresh:
            with bind_runtime(fresh):
                await fresh.core.bus.publish_outbound(
                    OutboundMessage("fake", "chat", "new")
                )
                await fresh.core.bus.drain_outbound()
        assert sent[-1] == ("account-B", "new")
    finally:
        await accepted.release()
        await asyncio.gather(publish, return_exceptions=True)
        await app.shutdown()


@pytest.mark.asyncio
async def test_channel_commit_failure_restores_old_transport_and_admission(
    tmp_path, monkeypatch
):
    sent = []
    _install_transport(monkeypatch, sent, tmp_path)
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        plugins=_config("account-A"),
    )
    app = AppRuntime(config, tmp_path, features=RuntimeFeatures(enable_proactive=False))
    await app.start()
    candidate = await app.prepare(replace(config, plugins=_config("account-B")))

    def fail():
        raise OSError("commit failed")

    try:
        with pytest.raises(OSError, match="commit failed"):
            await app.publish(candidate, commit=fail)
        await app.discard(candidate)
        assert app.generation == 1 and app._generation_manager.admission.is_set()
        await app.bus.publish_outbound(OutboundMessage("fake", "chat", "still A"))
        await app.bus.drain_outbound()
        assert sent == [("account-A", "still A")]
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_successful_account_switch_starts_untouched_candidate_background(
    tmp_path, monkeypatch
):
    app, candidate, loops = await _prepare_account_switch(tmp_path, monkeypatch)
    try:
        resume_after_commit = Mock(
            side_effect=AssertionError("barrier must not resume after commit")
        )
        monkeypatch.setattr(app.channel_host, "resume_intake", resume_after_commit)
        assert len(loops) == 2 and not loops[1].started.is_set()
        await asyncio.wait_for(app.publish(candidate), 3)
        await asyncio.wait_for(loops[1].started.wait(), 1)
        assert loops[0].stopped.is_set()
        assert loops[1].stop_calls == 0
        assert app.generation == 2 and app._generation_manager.admission.is_set()
        assert not app.channel_host.channels[0].paused
        resume_after_commit.assert_not_called()
    finally:
        await app.discard(candidate)
        await app.shutdown()


@pytest.mark.asyncio
async def test_failed_switch_restarts_only_published_background(tmp_path, monkeypatch):
    app, candidate, loops = await _prepare_account_switch(tmp_path, monkeypatch)

    def fail():
        raise OSError("commit failed")

    try:
        with pytest.raises(OSError, match="commit failed"):
            await asyncio.wait_for(app.publish(candidate, commit=fail), 3)
        assert len(loops) == 3
        await asyncio.wait_for(loops[2].started.wait(), 1)
        assert loops[0].stopped.is_set()
        assert loops[1].stop_calls == 0 and not loops[1].started.is_set()
        assert app.generation == 1 and app._generation_manager.admission.is_set()
    finally:
        await app.discard(candidate)
        await app.shutdown()


@pytest.mark.asyncio
async def test_pause_failure_reopens_admission_without_stopping_background(
    tmp_path, monkeypatch
):
    app, candidate, loops = await _prepare_account_switch(tmp_path, monkeypatch)

    def fail():
        raise RuntimeError("pause failed")

    monkeypatch.setattr(app.channel_host, "pause_intake", fail)
    try:
        with pytest.raises(RuntimeError, match="pause failed"):
            await app.publish(candidate)
        assert app._generation_manager.admission.is_set()
        assert len(loops) == 2 and loops[0].stop_calls == loops[1].stop_calls == 0
        assert app.generation == 1
    finally:
        await app.discard(candidate)
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recovery_phase", ["_prepare_background", "_publish_background"]
)
async def test_background_recovery_failure_preserves_errors_and_reopens_admission(
    tmp_path, monkeypatch, recovery_phase
):
    app, candidate, loops = await _prepare_account_switch(tmp_path, monkeypatch)

    def commit_failure():
        raise OSError("commit failed")

    def recovery_failure(*args):
        raise RuntimeError("background recovery failed")

    monkeypatch.setattr(app, recovery_phase, recovery_failure)
    try:
        with pytest.raises(
            ExceptionGroup, match="Channel handover recovery failed"
        ) as failure:
            await asyncio.wait_for(app.publish(candidate, commit=commit_failure), 3)
        assert [str(error) for error in failure.value.exceptions] == [
            "commit failed",
            "background recovery failed",
        ]
        assert app._generation_manager.admission.is_set()
        assert loops[1].stop_calls == 0
        assert app.generation == 1
    finally:
        await app.discard(candidate)
        await app.shutdown()


@pytest.mark.asyncio
async def test_rollback_resume_failure_still_reopens_admission(tmp_path, monkeypatch):
    app, candidate, loops = await _prepare_account_switch(tmp_path, monkeypatch)

    def fail():
        raise RuntimeError("resume failed")

    def commit_failure():
        raise OSError("commit failed")

    monkeypatch.setattr(app.channel_host, "resume_intake", fail)
    try:
        with pytest.raises(ExceptionGroup, match="Channel handover recovery failed"):
            await asyncio.wait_for(app.publish(candidate, commit=commit_failure), 3)
        await asyncio.wait_for(loops[2].started.wait(), 1)
        assert app._generation_manager.admission.is_set()
        assert app.generation == 1
    finally:
        await app.discard(candidate)
        await app.shutdown()


@pytest.mark.asyncio
async def test_account_switch_interrupts_background_work_that_ignores_stop(
    tmp_path, monkeypatch
):
    sent = []
    _install_transport(monkeypatch, sent, tmp_path)
    queued = asyncio.Event()
    interrupted = asyncio.Event()
    starts = []

    class StuckTick:
        # Hands a reply to the outbound queue, then hangs like a retried model call.
        def stop(self):
            pass

        async def run(self):
            lease = current_runtime_lease()
            assert lease is not None
            starts.append(lease.generation)
            if lease.generation > 1:
                return
            await lease.core.bus.publish_outbound(
                OutboundMessage("fake", "chat", "proactive old")
            )
            queued.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                interrupted.set()
                raise

    def build(*args, loop_consumer, **kwargs):
        loop = StuckTick()
        loop_consumer(loop)
        return [loop.run()], None

    monkeypatch.setattr(
        "bootstrap.runtime.background.build_memory_optimizer_task", build
    )
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        plugins=_config("account-A"),
    )
    app = AppRuntime(config, tmp_path, features=RuntimeFeatures(enable_proactive=False))
    await app.start()
    await asyncio.wait_for(queued.wait(), 1)
    candidate = await app.prepare(replace(config, plugins=_config("account-B")))
    publish = asyncio.create_task(app.publish(candidate))
    try:
        for _ in range(10):
            if not app.accepting_work:
                break
            await asyncio.sleep(0)
        assert not app.accepting_work
        request = asyncio.create_task(app.wait_for_admission())
        await asyncio.wait_for(publish, 3)
        await asyncio.wait_for(request, 1)
        assert interrupted.is_set()
        assert sent == [("account-A", "proactive old")]
        assert app.generation == 2 and app.accepting_work
        for _ in range(10):
            if starts == [1, 2]:
                break
            await asyncio.sleep(0)
        assert starts == [1, 2]
    finally:
        await asyncio.gather(publish, return_exceptions=True)
        await app.discard(candidate)
        await app.shutdown()
