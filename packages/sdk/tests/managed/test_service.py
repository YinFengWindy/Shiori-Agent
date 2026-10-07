"""Readiness is owned; another generation cannot start or recover before release."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from shiori_sdk.managed import service
from shiori_sdk.testing.processes import FakeProcesses


@pytest.fixture
def services(tmp_path, monkeypatch):
    events, tokens = [], {}
    readiness = asyncio.Event()
    readiness.set()

    async def respond(request):
        await readiness.wait()
        return httpx.Response(200, json={"token": tokens[str(request.url.port)]})

    class Child:
        def __init__(self, _processes):
            self.process = None

        async def start(self, command, **_kwargs):
            self.process = SimpleNamespace(returncode=None)
            tokens[command[0]] = command[1]
            events.append("start")

        async def close(self):
            if self.process is not None:
                events.extend(["kill", "wait"])
                self.process = None

    client_type = httpx.AsyncClient
    monkeypatch.setattr(service, "OwnedChild", Child)
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **_kwargs: client_type(transport=httpx.MockTransport(respond)),
    )

    def create():
        return service.OwnedService(
            tmp_path,
            FakeProcesses(),
            lambda path, port, token: ([str(port), token], path, {}),
        )

    return create, events, tokens, readiness


async def test_second_generation_waits_for_child_exit_before_recovery(
    tmp_path, services
):
    create, events, _tokens, _readiness = services
    old, new = create(), create()
    await old.start(tmp_path)

    async def recover():
        events.append("recover")

    new.before_start = recover
    waiting = asyncio.create_task(new.start(tmp_path))
    await asyncio.sleep(0.03)
    assert events == ["start"]
    await old.close()
    await waiting
    assert events == ["start", "kill", "wait", "recover", "start"]
    await new.close()


async def test_cancel_waiting_generation_never_stops_current_owner(tmp_path, services):
    create, events, _tokens, _readiness = services
    old, new = create(), create()
    await old.start(tmp_path)
    waiting = asyncio.create_task(new.start(tmp_path))
    await asyncio.sleep(0.03)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert old.require_url()
    assert events == ["start"]
    await old.close()


async def test_foreign_service_token_is_rejected_and_only_spawned_child_is_closed(
    tmp_path, services, monkeypatch
):
    create, events, tokens, _readiness = services
    instance = create()
    original = instance.child.start

    async def corrupt(command, **kwargs):
        await original(command, **kwargs)
        tokens[command[0]] = "foreign"

    monkeypatch.setattr(instance.child, "start", corrupt)
    with pytest.raises(RuntimeError, match="其他服务"):
        await instance.start(tmp_path)
    assert events == ["start", "kill", "wait"]
    with pytest.raises(RuntimeError, match="未运行"):
        instance.require_url()


async def test_live_child_is_not_callable_until_owned_health_is_ready(
    tmp_path, services
):
    create, events, _tokens, readiness = services
    readiness.clear()
    instance = create()
    starting = asyncio.create_task(instance.start(tmp_path))
    await asyncio.sleep(0.03)
    assert events == ["start"]
    with pytest.raises(RuntimeError, match="未运行"):
        instance.require_url()
    readiness.set()
    await starting
    assert instance.require_url().startswith("http://127.0.0.1:")
    await instance.close()


async def test_early_exit_names_the_last_output_line(tmp_path, monkeypatch):
    class Child:
        def __init__(self, _processes):
            self.process = None

        async def start(self, _command, **_kwargs):
            self.process = SimpleNamespace(returncode=3)

        async def exit_reason(self):
            return "ModuleNotFoundError: No module named 'torch'"

        async def close(self):
            self.process = None

    monkeypatch.setattr(service, "OwnedChild", Child)
    owned = service.OwnedService(
        tmp_path, FakeProcesses(), lambda path, port, token: ([], path, {})
    )
    with pytest.raises(RuntimeError) as failure:
        await owned.start(tmp_path)
    assert str(failure.value).startswith(
        "托管服务提前退出（3）：ModuleNotFoundError: No module named 'torch'。详见 "
    )
