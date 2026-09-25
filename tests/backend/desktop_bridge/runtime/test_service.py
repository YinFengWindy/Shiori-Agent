from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.config import load_config_text
from agent.provider import LLMProvider, LLMResponse
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.desktop_presence import DesktopPresence
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService
from desktop_bridge.runtime.service import _ServiceGeneration

_REGISTRATION = "00000000-0000-4000-a000-000000000001"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["runtime.apply", "plugin.config.set", "plugins.setEnabled"]
)
async def test_apply_notifications_distinguish_publication_from_replays(method):
    service = object.__new__(ReloadableDesktopService)
    result = {"plugin_id": "demo", "generation": 2, "changed": True}
    service.settings = SimpleNamespace(apply=AsyncMock(return_value=result))
    service.plugin_config = SimpleNamespace(set=AsyncMock(return_value=result))
    service.plugin_management = SimpleNamespace(
        set_enabled=AsyncMock(return_value=result)
    )
    transport = SimpleNamespace(publish_event=AsyncMock())
    service._current = _ServiceGeneration(
        transport, SimpleNamespace(generation=2), publication_pending=True
    )

    async def request():
        return await service.handle(
            {"id": "save", "method": method, "payload": {}},
            emit_event=lambda event: None,
        )

    response = await request()
    assert response.error is None
    transport.publish_event.assert_awaited_once_with(
        {"id": "save", "type": "event", "method": "runtime.applied", "payload": result}
    )
    replay = await request()
    assert replay.payload == response.payload == result
    assert replay.payload["changed"] is True
    assert transport.publish_event.await_args.args[0]["payload"] == {
        **result,
        "changed": False,
    }
    # A historical response remains idempotent after a later generation, without
    # falsely announcing the retired generation to current renderer contexts.
    service._current.lease.generation = 3
    assert (await request()).payload == result
    assert transport.publish_event.await_count == 2


@pytest.mark.asyncio
async def test_simultaneous_notifications_claim_publication_before_transport_await():
    entered = asyncio.Event()
    release = asyncio.Event()
    published = []

    async def publish(event):
        published.append(event)
        entered.set()
        await release.wait()

    service = object.__new__(ReloadableDesktopService)
    service._current = _ServiceGeneration(
        SimpleNamespace(publish_event=publish),
        SimpleNamespace(generation=2),
        publication_pending=True,
    )
    result = {"generation": 2, "changed": True}
    first = asyncio.create_task(service._notify_applied("first", result))
    await entered.wait()
    second = asyncio.create_task(service._notify_applied("replay", result))
    release.set()
    await asyncio.gather(first, second)
    assert [event["payload"]["changed"] for event in published] == [True, False]
    assert result["changed"] is True


@pytest.mark.asyncio
async def test_reloading_rejects_new_work_without_queuing_a_late_chat():
    service = object.__new__(ReloadableDesktopService)
    service.app = SimpleNamespace(accepting_work=False)
    service._owner = lambda *args: pytest.fail(
        "rejected request must never reach a handler"
    )
    response = await asyncio.wait_for(
        service.handle(
            {
                "method": "chat.send",
                "payload": {"role_id": "role", "content": "message"},
            },
            emit_event=lambda event: None,
        ),
        0.1,
    )
    assert response.error.code == "runtime_reloading"


@pytest.mark.asyncio
async def test_retirement_releases_generation_even_if_handler_cleanup_fails():
    handler = SimpleNamespace(
        chat_service=SimpleNamespace(drain=AsyncMock()),
        aclose=AsyncMock(side_effect=OSError("close failed")),
    )
    lease = SimpleNamespace(
        release=AsyncMock(), core=SimpleNamespace(plugin_manager=None)
    )
    entry = _ServiceGeneration(handler, lease)
    service = object.__new__(ReloadableDesktopService)
    service._entries = [entry]
    with pytest.raises(OSError, match="close failed"):
        await service._retire(entry)
    lease.release.assert_awaited_once()
    assert not service._entries


def _config(model=""):
    registration = (
        f'[[llm.registrations]]\nid = "{_REGISTRATION}"\nprovider = "openai"\n'
        f'model = "{model}"\napi_key = "fake-key"\n'
        if model
        else "[llm]\nregistrations = []\n"
    )
    return (
        registration
        + '\n[agent.maintenance]\nmemory_optimizer_enabled = false\n[proactive]\nenabled = false\nprofile = "quiet"\n'
    )


@pytest.mark.asyncio
async def test_runtime_apply_retries_and_noops_preserve_generation_notifications(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda workspace: [])
    path = tmp_path / "config.toml"
    path.write_text(_config(), encoding="utf-8")
    app = AppRuntime(
        load_config_text(_config()),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    events = []
    service.add_event_listener(events.append)

    async def apply(payload):
        response = await service.handle(
            {"method": "runtime.apply", "payload": payload},
            emit_event=lambda event: None,
        )
        assert response.error is None, response.error
        return response.payload

    try:
        payload = {"config_toml": _config("first"), "operation_id": "first"}
        first, replay = await asyncio.gather(apply(payload), apply(payload))
        assert first == replay == {"generation": 2, "changed": True}
        assert [event["payload"]["changed"] for event in events] == [True, False]
        noop = await apply({**payload, "operation_id": "noop"})
        assert noop == {"generation": 2, "changed": False}
        assert events[-1]["payload"] == noop
        second = await apply(
            {"config_toml": _config("second"), "operation_id": "second"}
        )
        assert second == {"generation": 3, "changed": True}
        assert events[-1]["payload"] == second
        count = len(events)
        assert await apply(payload) == first
        assert len(events) == count
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_empty_boot_register_bind_and_chat_preserves_existing_turn(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda workspace: [])
    calls = []
    seed_calls = []
    entered = asyncio.Event()
    finish = asyncio.Event()
    hold = False

    async def fake_chat(self, **kwargs):
        model = kwargs["model"]
        calls.append(model)
        if "首版 SELF.md" in str(kwargs["messages"][0].get("content")):
            seed_calls.append(model)
        if hold and model == "first":
            entered.set()
            await finish.wait()
        content = f"reply from {model}"
        if kwargs.get("response_format"):
            content = json.dumps(
                {"content": content, "mood": "平静", "thought": "我记得我们的约定。"},
                ensure_ascii=False,
            )
        return LLMResponse(content=content)

    monkeypatch.setattr(LLMProvider, "chat", fake_chat)
    path = tmp_path / "config.toml"
    path.write_text(_config(), encoding="utf-8")
    app = AppRuntime(
        load_config_text(_config()),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    events = []

    async def request(method, payload=None):
        response = await service.handle(
            {"id": method, "method": method, "payload": payload or {}},
            emit_event=events.append,
        )
        assert response.error is None, response.error
        return response.payload

    try:
        assert (await request("health"))["ok"]
        created = await request(
            "roles.create", {"name": "Role", "system_prompt": "Role prompt"}
        )
        role_id = created["role"]["id"]
        await request("session.openByRole", {"role_id": role_id})
        assert calls == []
        unbound = await service.handle(
            {"method": "chat.send", "payload": {"role_id": role_id, "content": "hi"}},
            emit_event=events.append,
        )
        assert unbound.error.code == "model_configuration_required"
        assert not app.session_manager.get_or_create(f"role:{role_id}").messages
        await request(
            "runtime.apply",
            {
                "config_toml": _config("first"),
                "operation_id": "first",
                "expected_generation": 1,
            },
        )
        assert not service.roles.get_role(role_id).runtime_config[
            "dialogue_model_registration_id"
        ]
        await request(
            "roles.update",
            {
                "role_id": role_id,
                "runtime_config": {
                    "dialogue_model_registration_id": _REGISTRATION,
                },
            },
        )
        assert calls == []
        hold = True
        await request(
            "chat.send", {"role_id": role_id, "content": "old task", "turn_id": "old"}
        )
        await asyncio.wait_for(entered.wait(), 5)
        old_service = service._current.service
        await request(
            "runtime.apply",
            {
                "config_toml": _config("second"),
                "operation_id": "second",
                "expected_generation": 2,
            },
        )
        assert old_service.chat_service.is_busy(f"role:{role_id}")
        assert not finish.is_set()
        assert app.generation == 3
        assert (await request("runtime.status"))["config_toml"] == _config("second")
        finish.set()
        await asyncio.wait_for(old_service.chat_service.drain(), 5)
        await request(
            "chat.send", {"role_id": role_id, "content": "new task", "turn_id": "new"}
        )
        await asyncio.wait_for(service._current.service.chat_service.drain(), 5)
        assert calls[-1] == "second"
        assert seed_calls == ["first"]
        assert (
            service.roles.get_role(role_id).memory_init_state["self_seed"]["status"]
            == "generated"
        )
        assert any(item["method"] == "chat.done" for item in events)
        await request(
            "runtime.apply",
            {
                "config_toml": _config(),
                "operation_id": "empty",
                "expected_generation": 3,
                "role_model_updates": [
                    {
                        "role_id": role_id,
                        "runtime_config": {
                            "dialogue_model_registration_id": "",
                        },
                    }
                ],
            },
        )
        assert not service.status()["models_registered"]
        assert (await request("health"))["ok"]
        assert app.session_manager.get_or_create(f"role:{role_id}").messages
    finally:
        finish.set()
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_invalid_apply_and_generation_conflict_preserve_active_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda workspace: [])
    path = tmp_path / "config.toml"
    path.write_text(_config(), encoding="utf-8")
    app = AppRuntime(
        load_config_text(_config()),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    try:
        for text, expected, code in [
            ("invalid TOML", 1, "runtime_config_invalid"),
            (_config("model"), 9, "runtime_generation_conflict"),
        ]:
            response = await service.handle(
                {
                    "method": "runtime.apply",
                    "payload": {
                        "config_toml": text,
                        "operation_id": code,
                        "expected_generation": expected,
                    },
                },
                emit_event=lambda event: None,
            )
            assert response.error.code == code
            assert path.read_text(encoding="utf-8") == _config()
            assert app.generation == 1
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_first_chat_seed_failure_reports_error_and_next_chat_retries(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda workspace: [])
    seeds, content_replies, mood_replies = [], [], []
    fail_seed = True

    async def fake_chat(self, **kwargs):
        if "首版 SELF.md" in str(kwargs["messages"][0].get("content")):
            seeds.append(kwargs["model"])
            if fail_seed:
                raise RuntimeError("seed provider unavailable")
            return LLMResponse(content="# 我是谁\n\n我是本地测试角色。")
        if kwargs.get("response_format") == {"type": "json_object"}:
            # The mood follow-up remains auxiliary through role routing; the
            # resolved provider applies the cap when it can disable thinking.
            assert kwargs["call_purpose"] == "auxiliary"
            assert kwargs["auxiliary_max_tokens"] == 512
            mood_replies.append(kwargs["model"])
            return LLMResponse(
                content='{"mood":"平静","thought":"我终于能和你说话了。"}'
            )
        content_replies.append(kwargs["model"])
        assert "response_format" not in kwargs
        assert kwargs["call_purpose"] == "default"
        return LLMResponse(content="你好。")

    monkeypatch.setattr(LLMProvider, "chat", fake_chat)
    path = tmp_path / "config.toml"
    path.write_text(_config("selected"), encoding="utf-8")
    app = AppRuntime(
        load_config_text(_config("selected")),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    events = []

    async def request(method, payload):
        response = await service.handle(
            {"id": method, "method": method, "payload": payload},
            emit_event=events.append,
        )
        assert response.error is None, response.error
        return response.payload

    try:
        created = await request(
            "roles.create", {"name": "Mira", "system_prompt": "Be Mira"}
        )
        role_id = created["role"]["id"]
        # New roles default to the first registered model (the only one here).
        assert (
            created["role"]["runtime_config"]["dialogue_model_registration_id"]
            == _REGISTRATION
        )
        await request(
            "roles.update",
            {
                "role_id": role_id,
                "runtime_config": {"dialogue_model_registration_id": _REGISTRATION},
            },
        )
        await request("session.openByRole", {"role_id": role_id})
        assert seeds == content_replies == mood_replies == []
        self_path = tmp_path / "roles" / role_id / "memory/SELF.md"
        default = self_path.read_text(encoding="utf-8")
        await request(
            "chat.send", {"role_id": role_id, "content": "你好", "turn_id": "first"}
        )
        await asyncio.wait_for(service._current.service.chat_service.drain(), 5)
        assert seeds == ["selected"]
        assert content_replies == mood_replies == []
        assert any(event["method"] == "chat.error" for event in events)
        assert self_path.read_text(encoding="utf-8") == default
        assert (
            service.roles.get_role(role_id).memory_init_state["self_seed"]["last_error"]
            == "seed provider unavailable"
        )
        fail_seed = False
        for turn_id in ("retry", "subsequent"):
            await request(
                "chat.send", {"role_id": role_id, "content": "你好", "turn_id": turn_id}
            )
            await asyncio.wait_for(service._current.service.chat_service.drain(), 5)
        assert seeds == ["selected", "selected"]
        # Each of the two turns (retry, subsequent) produces exactly one
        # content reply and one mood follow-up - not just "at least 2" total,
        # which a single turn making both calls could also satisfy.
        assert content_replies == ["selected", "selected"]
        assert mood_replies == ["selected", "selected"]
        assert (
            service.roles.get_role(role_id).memory_init_state["self_seed"]["status"]
            == "generated"
        )
        assert any(event["method"] == "chat.done" for event in events)
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_settings_form_route_preserves_latest_plugins_but_raw_apply_can_remove_them(
    tmp_path, monkeypatch
):
    import tomllib

    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda workspace: [])
    initial = (
        _config() + '\n[plugins.qqbot]\napp_id = "old"\nclient_secret = "secret"\n'
    )
    path = tmp_path / "config.toml"
    path.write_text(initial, encoding="utf-8")
    app = AppRuntime(
        load_config_text(initial),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))

    async def request(payload):
        return await service.handle(
            {"method": "runtime.apply", "payload": payload},
            emit_event=lambda event: None,
        )

    try:
        current = (
            _config()
            + '\n[plugins.qqbot]\napp_id = "new"\nclient_secret = "new-secret"\n[plugins."unknown.id"]\nitems = [{ label = "keep", numbers = [1, 2] }]\n'
        )
        response = await request(
            {"config_toml": current, "operation_id": "plugin-write"}
        )
        assert response.error is None
        draft = {
            "config_toml": _config() + "\n[agent]\nmax_tokens = 4096\n",
            "preserve_plugins": True,
            "operation_id": "form-save",
        }
        response = await request(draft)
        assert response.error is None, response.error
        assert (
            tomllib.loads(path.read_text(encoding="utf-8"))["plugins"]
            == tomllib.loads(current)["plugins"]
        )
        after_form = path.read_bytes()
        assert (await request(draft)).payload == response.payload
        assert path.read_bytes() == after_form
        assert (
            await request({"config_toml": _config(), "operation_id": "raw-remove"})
        ).error is None
        assert "plugins" not in tomllib.loads(path.read_text(encoding="utf-8"))
        # Retrying the form after another write must not resurrect stale plugins.
        assert (await request(draft)).payload == response.payload
        assert "plugins" not in tomllib.loads(path.read_text(encoding="utf-8"))
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_restart_required_refuses_all_hot_write_routes_before_candidate_or_persistence(
    tmp_path, monkeypatch
):
    from pathlib import Path
    from shiori_plugin_testkit.packages import stage_plugin_package

    root = tmp_path / "packages"
    stage_plugin_package(
        Path(__file__).resolve().parents[3] / "fixtures/plugins/restart_required",
        root / "restart_required",
    )
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda workspace: [root]
    )
    text = (
        _config("model")
        + '\n[plugins.restart_required]\nvalue = "first"\nenabled = true\n'
    )
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    app = AppRuntime(
        load_config_text(text),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    roles = RoleStore(tmp_path)
    role = roles.create_role(name="Role", system_prompt="Role", role_id="role")
    service = ReloadableDesktopService(app, path, roles)
    published = []
    service.add_event_listener(published.append)
    state = app.core.plugin_manager._dependency_api("restart_required")
    build = AsyncMock(side_effect=AssertionError("candidate must not start"))
    monkeypatch.setattr("bootstrap.runtime.reload.prepare_core_runtime", build)

    async def request(method, payload):
        return await service.handle(
            {"method": method, "payload": payload}, emit_event=lambda event: None
        )

    try:
        listed = await request("plugins.list", {})
        assert listed.payload["plugins"][0]["supports_hot_unload"] is False
        no_op = await request(
            "runtime.apply", {"config_toml": text, "operation_id": "noop"}
        )
        assert no_op.error is None
        assert published[-1]["payload"]["changed"] is False
        role_only = await request(
            "runtime.apply",
            {
                "config_toml": text,
                "operation_id": "role-only",
                "role_model_updates": [
                    {
                        "role_id": role.id,
                        "runtime_config": {
                            "dialogue_model_registration_id": _REGISTRATION
                        },
                    }
                ],
            },
        )
        assert role_only.error is None, role_only.error
        assert role_only.payload["changed"] is True
        assert published[-1]["payload"] == {"generation": 1, "changed": False}
        assert (
            roles.get_role(role.id).runtime_config["dialogue_model_registration_id"]
            == _REGISTRATION
        )
        before = path.read_bytes()
        for index, (method, payload) in enumerate(
            [
                (
                    "runtime.apply",
                    {
                        "config_toml": text.replace(
                            'model = "model"', 'model = "changed"'
                        ),
                        "role_model_updates": [
                            {
                                "role_id": role.id,
                                "runtime_config": {
                                    "dialogue_model_registration_id": ""
                                },
                            }
                        ],
                    },
                ),
                (
                    "runtime.apply",
                    {"config_toml": _config("changed"), "preserve_plugins": True},
                ),
                (
                    "plugins.setEnabled",
                    {"plugin_id": "restart_required", "enabled": False},
                ),
                (
                    "plugin.config.set",
                    {"plugin_id": "restart_required", "values": {"value": "changed"}},
                ),
            ]
        ):
            response = await request(
                method, {**payload, "operation_id": f"blocked-{index}"}
            )
            assert response.error.code == "plugin_restart_required", response.error
            assert response.error.details["plugin_ids"] == ["restart_required"]
            assert "未保存" in response.error.message
            assert path.read_bytes() == before
            assert (
                roles.get_role(role.id).runtime_config["dialogue_model_registration_id"]
                == _REGISTRATION
            )
            assert app.generation == 1
            assert state == ["started"]
        build.assert_not_awaited()
    finally:
        await service.aclose()
        await app.shutdown()
    assert state == ["started", "closed"]


@pytest.mark.asyncio
async def test_presence_report_updates_app_state_even_while_reloading():
    service = object.__new__(ReloadableDesktopService)
    presence = DesktopPresence()
    service.app = SimpleNamespace(accepting_work=False, desktop_presence=presence)
    service._owner = lambda *args: pytest.fail(
        "presence is app state, never a generation's"
    )

    async def report(payload):
        return await service.handle(
            {"id": "p", "method": "desktop.presence.report", "payload": payload},
            emit_event=lambda event: None,
        )

    away = await report({"present": False})
    assert away.error is None
    assert away.payload == {"present": False}
    assert presence.is_desktop_present() is False
    assert (await report({"present": True})).payload == {"present": True}
    assert presence.is_desktop_present() is True
    invalid = await report({"present": "no"})
    assert invalid.error.code == "invalid_request"
    assert presence.is_desktop_present() is True
