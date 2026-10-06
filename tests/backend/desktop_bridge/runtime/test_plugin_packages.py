"""Explicit package confirmation cannot silently overwrite or trust changed bytes."""

import shutil

import pytest

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_archive import extract_package_zip
from desktop_bridge.runtime.apply import RuntimeApplyError


def test_cancel_removes_preview_without_installing_or_trusting(plugin_package_env):
    env = plugin_package_env
    preview = env.preview()
    assert preview["action"] == "install"
    assert not env.target.exists()
    assert not (env.workspace / "private_runtime/plugin-trust.json").exists()
    env.packages.cancel({"token": preview["token"]})
    assert env.packages.store.list() == []
    assert list(env.packages.store.root.iterdir()) == []


def test_retrying_confirmation_after_lost_response_is_idempotent(plugin_package_env):
    env = plugin_package_env
    operation = env.confirm()
    result = env.packages.confirm({"token": operation.token, "trusted": True})
    assert result["restart_required"] is True
    assert len(env.packages.store.list()) == 1
    assert not env.target.exists()


def test_preview_shows_original_zip_name_without_native_staging_prefix(
    plugin_package_env,
):
    env = plugin_package_env
    source = env.archive()
    staged = source.with_name("b397883e-7d88-4c5c-8cdd-351c27cdd69b-" + source.name)
    source.rename(staged)
    result = env.packages.preview({"source": str(staged)})
    assert result["source_name"] == source.name


@pytest.mark.parametrize("change", ["no-confirmation", "staging", "target", "conflict"])
def test_confirmation_rejects_missing_trust_and_changed_snapshots(
    plugin_package_env, change
):
    env = plugin_package_env
    preview = env.preview()
    token = preview["token"]
    if change == "staging":
        (env.packages.store.directory(token) / "package/backend/plugin.py").write_text(
            "raise RuntimeError('changed')", encoding="utf-8"
        )
    elif change == "target":
        extract_package_zip(env.archive(), env.target)
    elif change == "conflict":
        extract_package_zip(env.archive(), env.workspace / "plugins/duplicate")
    with pytest.raises(ValueError):
        env.packages.confirm({"token": token, "trusted": change != "no-confirmation"})
    assert env.packages.store.read(token).status == "preview"
    assert not (env.workspace / "private_runtime/plugin-trust.json").exists()


@pytest.mark.parametrize("conflict", ["builtin", "duplicate", "existing", "wrong-id"])
def test_install_update_rejects_ambiguous_targets(plugin_package_env, conflict):
    env = plugin_package_env
    root = env.builtins / "demo" if conflict == "builtin" else env.target
    extract_package_zip(env.archive(), root)
    if conflict == "duplicate":
        shutil.copytree(root, env.workspace / "plugins/duplicate")
    candidate = "" if conflict == "existing" else str(root)
    with pytest.raises(ValueError):
        env.preview(
            candidate_id=candidate,
            plugin_id="other" if conflict == "wrong-id" else "demo",
        )
    assert list(env.packages.store.root.iterdir()) == []
    assert (root / "manifest.yaml").exists()


def test_invalid_archive_leaves_no_partial_package(plugin_package_env):
    env = plugin_package_env
    with pytest.raises(PackageContractError):
        env.preview(invalid=True)
    assert not env.target.exists()
    assert list(env.packages.store.root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", [False, True])
async def test_uninstall_uses_existing_hot_disable_and_defers_unsafe_unload(
    plugin_package_env, unsafe
):
    env = plugin_package_env
    extract_package_zip(env.archive(), env.target)
    if unsafe:
        env.management.set_enabled.side_effect = RuntimeApplyError(
            "plugin_restart_required", "needs restart"
        )
    result = await env.packages.uninstall(
        {
            "candidate_id": str(env.target),
            "delete_data": False,
            "operation_id": "remove",
        }
    )
    assert result["restart_required"]
    env.management.set_enabled.assert_awaited_once()
    assert env.management.set_enabled.call_args.args[0]["enabled"] is False
    assert env.target.exists()
    [operation] = env.packages.store.list()
    assert operation.status == "pending" and operation.action == "uninstall"
    assert not operation.delete_data


@pytest.mark.asyncio
async def test_uninstall_does_not_queue_after_failed_resource_cleanup(
    plugin_package_env,
):
    env = plugin_package_env
    extract_package_zip(env.archive(), env.target)
    env.management.set_enabled.side_effect = RuntimeApplyError(
        "runtime_apply_failed", "cleanup failed"
    )
    with pytest.raises(RuntimeApplyError, match="cleanup failed"):
        await env.packages.uninstall(
            {"candidate_id": str(env.target), "operation_id": "remove"}
        )
    assert env.packages.store.list() == []
    assert env.target.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin_id, kind, provider_id, label",
    [
        ("tencent_asr", "asr", "tencent", "腾讯语音识别"),
        ("minimax_tts", "tts", "minimax", "MiniMax 语音合成"),
    ],
)
async def test_shipped_voice_packages_support_real_update_uninstall_and_reinstall(
    tmp_path, monkeypatch, plugin_id, kind, provider_id, label
):
    import io
    import json
    import wave
    from types import SimpleNamespace
    from zipfile import ZipFile
    from agent.config import load_config_data, load_config_text
    from agent.plugin_host.kernel import HostServices, PluginKernel
    from bootstrap.tools import _resolve_plugin_dirs
    from bootstrap.bundled_plugins import ensure_bundled_plugins
    from bus.event_bus import EventBus
    from desktop_bridge.runtime.plugin_packages import RuntimePluginPackages
    from desktop_bridge.runtime.plugin_package_transaction import (
        apply_pending_plugin_operations,
    )
    from desktop_bridge.voice.voice_service import VoiceService
    from infra.persistence.toml_store import render_toml

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = workspace / "config.toml"
    data = {
        "voice": {"enabled": True, "asr": {"enabled": True}, "tts": {"enabled": True}},
        "plugins": {
            "tencent_asr": {
                "enabled": True,
                "secret_id": "old-id",
                "secret_key": "old-secret",
            },
            "minimax_tts": {"enabled": True, "api_key": "old-key"},
        },
    }
    config_path.write_text(render_toml(data), encoding="utf-8")
    config = load_config_data(data)
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "first-session")
    roots = _resolve_plugin_dirs(workspace)
    target = workspace / "plugins" / plugin_id

    def make_kernel():
        return PluginKernel(
            roots,
            external_plugin_dirs=[workspace / "plugins"],
            services=HostServices(
                event_bus=EventBus(),
                workspace=workspace,
                plugin_configs=load_config_text(
                    config_path.read_text(encoding="utf-8")
                ).plugins,
            ),
        )

    kernel = make_kernel()
    current = {"kernel": kernel}

    async def disable(payload, **_kwargs):
        await current["kernel"].unload(payload["plugin_id"])
        return {"generation": 2}

    management = SimpleNamespace(
        _plugin_kernel=lambda: current["kernel"],
        list=lambda _: {
            "plugins": [
                {"candidate_id": row.candidate_id, "enabled": True, "can_toggle": True}
                for row in current["kernel"].inspect_candidates()
            ]
        },
        set_enabled=disable,
    )
    packages = RuntimePluginPackages(management, workspace)
    imports = workspace / "private_runtime/imports/plugin-packages"
    imports.mkdir(parents=True)
    archive = imports / f"{plugin_id}.zip"
    with ZipFile(archive, "w") as output:
        for source in target.rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            content = source.read_text(encoding="utf-8")
            if source.name == "manifest.yaml":
                content = content.replace("version: '0.1.0'", "version: '0.2.0'")
            elif source.name == "client.py":
                content = content.replace(label, label + "新版")
            output.writestr(source.relative_to(target).as_posix(), content)
    updated_archive = archive.read_bytes()
    try:
        assert await kernel.load(plugin_id)
        [record] = [row for row in kernel.discover() if row.manifest.id == plugin_id]
        assert record.source == "workspace" and record.plugin_dir == target
        assert record.admission is None
        assert record.manifest.version == "0.1.0"
        preview = packages.preview(
            {"source": str(archive), "candidate_id": str(target)}
        )
        assert preview["action"] == "update"
        assert preview["previous_version"] == "0.1.0"
        packages.confirm({"token": preview["token"], "trusted": True})
        apply_pending_plugin_operations(workspace, config_path)
        assert "version: '0.1.0'" in (target / "manifest.yaml").read_text(
            encoding="utf-8"
        )
        await kernel.terminate_all()
        monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "second-session")
        apply_pending_plugin_operations(workspace, config_path)
        ensure_bundled_plugins(workspace)
        kernel = make_kernel()
        current["kernel"] = kernel
        assert await kernel.load(plugin_id)
        [record] = [row for row in kernel.discover() if row.manifest.id == plugin_id]
        assert record.manifest.version == "0.2.0"
        provider = (
            kernel.voice.asr(provider_id)
            if kind == "asr"
            else kernel.voice.tts(provider_id)
        )
        assert provider.info.label == label + "新版"
        assert (
            load_config_text(config_path.read_text(encoding="utf-8")).plugins
            == config.plugins
        )

        calls = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"Response":{"Result":"heard","RequestId":"retained"}}'

            def __iter__(self):
                yield b'data: {"data":{"audio":"0102"}}\n'

        def request(req, *, timeout):
            calls.append((dict(req.headers), json.loads(req.data)))
            return Response()

        monkeypatch.setattr("urllib.request.urlopen", request)
        service = VoiceService(config.voice, kernel.voice)
        if kind == "asr":
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(16000)
                writer.writeframes(b"\0" * 32000)
            assert service.transcribe(buffer.getvalue()) == "heard"
            assert "Credential=old-id/" in calls[0][0]["Authorization"]
        else:
            assert (
                service.synthesize(
                    "old role", voice_id="old-role-voice", speed=1.3, emotion="happy"
                )
                == b"\1\2"
            )
            assert calls[0][0]["Authorization"] == "Bearer old-key"
            assert calls[0][1]["voice_setting"]["voice_id"] == "old-role-voice"

        private_data = workspace / "plugin-data" / plugin_id
        private_data.mkdir(parents=True)
        (private_data / "old.json").write_text("{}", encoding="utf-8")
        await packages.uninstall(
            {"candidate_id": str(target), "delete_data": True, "operation_id": "remove"}
        )
        await kernel.terminate_all()
        monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "third-session")
        apply_pending_plugin_operations(workspace, config_path)
        ensure_bundled_plugins(workspace)
        assert not target.exists()
        assert not private_data.exists()
        assert (
            workspace
            / "private_runtime/bundled-plugin-seeds"
            / plugin_id
            / "receipt.json"
        ).is_file()
        archive.write_bytes(updated_archive)
        preview = packages.preview({"source": str(archive)})
        assert preview["action"] == "install"
        packages.confirm({"token": preview["token"], "trusted": True})
        monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "fourth-session")
        apply_pending_plugin_operations(workspace, config_path)
        kernel = make_kernel()
        current["kernel"] = kernel
        assert await kernel.load(plugin_id)
        assert (
            next(
                row for row in kernel.discover() if row.manifest.id == plugin_id
            ).manifest.version
            == "0.2.0"
        )
    finally:
        await kernel.terminate_all()
