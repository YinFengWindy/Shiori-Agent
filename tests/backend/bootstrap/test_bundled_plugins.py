"""First install inherits only shipped bytes; later user changes remain authoritative."""

import json
import shutil
import pytest
from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore
from bootstrap import bundled_plugins
from bootstrap.plugin_distribution import bundled_plugin_sources


@pytest.fixture
def shipped(monkeypatch):
    sources = bundled_plugin_sources()
    monkeypatch.setattr(
        bundled_plugins,
        "bundled_plugin_sources",
        lambda: {"tencent_asr": sources["tencent_asr"]},
    )
    return sources["tencent_asr"]


def test_first_install_is_trusted_immediately_and_never_restored_after_removal(
    tmp_path, monkeypatch, shipped
):
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "current-session")
    bundled_plugins.ensure_bundled_plugins(tmp_path)
    target = tmp_path / "plugins/tencent_asr"
    assert (target / "README.md").is_file()
    assert not (target / "tests").exists()
    assert PluginTrustStore(tmp_path).is_trusted(
        target, inspect_package_content(target).fingerprint, activation=True
    )
    shutil.rmtree(target)
    bundled_plugins.ensure_bundled_plugins(tmp_path)
    assert not target.exists()


def test_preexisting_package_is_neither_overwritten_nor_automatically_trusted(
    tmp_path, shipped
):
    target = tmp_path / "plugins/tencent_asr"
    shutil.copytree(
        shipped,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "tests", "build", "*.egg-info"),
    )
    entry = target / "backend/plugin.py"
    entry.write_text("# user version\n", encoding="utf-8")
    bundled_plugins.ensure_bundled_plugins(tmp_path)
    assert entry.read_text(encoding="utf-8") == "# user version\n"
    assert not PluginTrustStore(tmp_path).is_trusted(
        target, inspect_package_content(target).fingerprint
    )


def test_restart_recovers_publication_interrupted_before_trust(
    tmp_path, monkeypatch, shipped
):
    original = PluginTrustStore.approve
    with monkeypatch.context() as patch:
        patch.setattr(
            PluginTrustStore,
            "approve",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("interrupted")),
        )
        with pytest.raises(OSError, match="interrupted"):
            bundled_plugins.ensure_bundled_plugins(tmp_path)
    target = tmp_path / "plugins/tencent_asr"
    assert target.exists()
    assert not PluginTrustStore(tmp_path).is_trusted(
        target, inspect_package_content(target).fingerprint
    )
    assert PluginTrustStore.approve is original
    bundled_plugins.ensure_bundled_plugins(tmp_path)
    assert PluginTrustStore(tmp_path).is_trusted(
        target, inspect_package_content(target).fingerprint, activation=True
    )
    receipt = tmp_path / "private_runtime/bundled-plugin-seeds/tencent_asr/receipt.json"
    assert json.loads(receipt.read_text(encoding="utf-8"))["state"] == "complete"


def test_changed_copy_after_interruption_never_inherits_trust(
    tmp_path, monkeypatch, shipped
):
    with monkeypatch.context() as patch:
        patch.setattr(
            PluginTrustStore,
            "approve",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("interrupted")),
        )
        with pytest.raises(OSError):
            bundled_plugins.ensure_bundled_plugins(tmp_path)
    target = tmp_path / "plugins/tencent_asr"
    (target / "backend/plugin.py").write_text("# changed\n", encoding="utf-8")
    bundled_plugins.ensure_bundled_plugins(tmp_path)
    assert (target / "backend/plugin.py").read_text(encoding="utf-8") == "# changed\n"
    assert not PluginTrustStore(tmp_path).is_trusted(
        target, inspect_package_content(target).fingerprint
    )


@pytest.mark.parametrize("linked_parent", ["plugins", "private_runtime"])
def test_directory_links_cannot_redirect_seed_writes(tmp_path, linked_parent, shipped):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    try:
        (workspace / linked_parent).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks requires platform permission")
    with pytest.raises(ValueError, match="不能包含链接"):
        bundled_plugins.ensure_bundled_plugins(workspace)
    assert list(outside.iterdir()) == []


def test_no_shipped_provider_does_not_fail_or_create_installation_receipts(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bundled_plugins, "bundled_plugin_sources", lambda: {})
    bundled_plugins.ensure_bundled_plugins(tmp_path)
    assert list(tmp_path.iterdir()) == []
