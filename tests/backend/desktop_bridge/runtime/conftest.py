"""Filesystem package fixtures shared by the installer and its restart transaction."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from agent.plugin_host.discovery import discover_plugins
from desktop_bridge.runtime.plugin_packages import RuntimePluginPackages


@pytest.fixture
def plugin_package_env(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    config = workspace / "config.toml"
    config.write_text(
        '[llm]\nregistrations = []\n[plugins.demo]\nenabled = false\nnote = "keep"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "session-a")
    monkeypatch.setattr(
        "desktop_bridge.runtime.plugin_package_transaction.plugin_roots",
        lambda: [builtins],
    )

    def records():
        root = workspace / "plugins"
        return discover_plugins(
            [builtins, root],
            external_roots=[root],
            namespace="test",
            strict=False,
            host=None,
        )

    management = SimpleNamespace(
        _plugin_kernel=lambda: SimpleNamespace(inspect_candidates=records),
        list=lambda _: {
            "plugins": [
                {"candidate_id": row.candidate_id, "can_toggle": True, "enabled": True}
                for row in records()
            ]
        },
        set_enabled=AsyncMock(return_value={"generation": 2}),
    )
    packages = RuntimePluginPackages(management, workspace)

    def archive(version="1.0.0", plugin_id="demo", *, hot=True, invalid=False):
        root = workspace / "private_runtime/imports/plugin-packages"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{plugin_id}-{version}.zip"
        with ZipFile(path, "w") as output:
            output.writestr(
                "manifest.yaml",
                f"api: 2\npackage_contract: 1\nid: {plugin_id}\nversion: {version}\nruntime_api: '>=2.0.0 <3.0.0'\nentry: backend/plugin.py\ncapabilities: [rpc]\nsupports_hot_unload: {str(hot).lower()}\n",
            )
            if not invalid:
                output.writestr(
                    "backend/plugin.py",
                    f"VERSION = '{version}'\nasync def setup(ctx):\n    pass\n",
                )
        return path

    def preview(version="1.0.0", candidate_id="", **kwargs):
        return packages.preview(
            {"source": str(archive(version, **kwargs)), "candidate_id": candidate_id}
        )

    def confirm(version="1.0.0", candidate_id="", **kwargs):
        result = preview(version, candidate_id, **kwargs)
        packages.confirm({"token": result["token"], "trusted": True})
        return packages.store.read(result["token"])

    return SimpleNamespace(
        workspace=workspace,
        config=config,
        builtins=builtins,
        packages=packages,
        management=management,
        archive=archive,
        preview=preview,
        confirm=confirm,
        target=workspace / "plugins/demo",
    )
