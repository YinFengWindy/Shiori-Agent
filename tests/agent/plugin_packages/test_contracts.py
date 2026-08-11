from __future__ import annotations

import pytest

from agent.plugin_packages.contracts import PluginManifest, PluginManifestError


def _manifest(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "plugin_id": "desktop-pet",
        "name": "Desktop Pet",
        "description": "Desktop overlay pet",
        "version": "1.0.0",
        "plugin_api_version": 1,
        "platforms": [{"os": "win32", "arch": "x64"}],
        "entrypoints": {
            "backend": "backend/main.py",
            "desktop": "desktop/index.html",
        },
        "capabilities": ["agent.tool", "desktop.overlay", "plugin.rpc"],
        "permissions": ["plugin.storage"],
        "tools": [
            {
                "remote_name": "pet_action",
                "name": "pet_action",
                "risk": "external-side-effect",
                "always_on": True,
                "search_hint": "desktop pet action",
            }
        ],
        "rpc_methods": [
            {"method": "pet.state", "remote_name": "pet_state"},
        ],
        "desktop_contributions": [
            {
                "id": "pet-overlay",
                "kind": "overlay",
                "entrypoint": "desktop/index.html",
                "width": 480,
                "height": 680,
                "transparent": True,
                "always_on_top": True,
            }
        ],
        "release": {
            "asset": "desktop-pet-1.0.0-win32-x64.zip",
            "checksums_asset": "checksums.json",
        },
    }
    value.update(overrides)
    return value


def test_manifest_validates_host_and_serializes_contract() -> None:
    manifest = PluginManifest.from_mapping(_manifest(), source="test")

    assert manifest.supports_host(os_name="win32", arch="x64", api_version=1)
    assert not manifest.supports_host(os_name="linux", arch="x64", api_version=1)
    assert manifest.to_dict()["plugin_id"] == "desktop-pet"
    assert manifest.tools[0].name == "pet_action"
    assert manifest.rpc_methods[0].method == "pet.state"
    assert manifest.desktop_contributions[0].entrypoint == "desktop/index.html"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plugin_id", "../pet"),
        ("version", "latest"),
        ("entrypoints", {"backend": "..\\outside.py"}),
        (
            "release",
            {"asset": "C:/outside.zip", "checksums_asset": "checksums.json"},
        ),
    ],
)
def test_manifest_rejects_unsafe_or_unversioned_contracts(
    field: str,
    value: object,
) -> None:
    with pytest.raises(PluginManifestError):
        PluginManifest.from_mapping(_manifest(**{field: value}), source="test")


def test_manifest_rejects_duplicate_capabilities() -> None:
    with pytest.raises(PluginManifestError, match="duplicate capabilities"):
        PluginManifest.from_mapping(
            _manifest(capabilities=["agent.tool", "agent.tool"]),
            source="test",
        )


def test_manifest_rejects_tools_without_the_agent_tool_capability() -> None:
    with pytest.raises(PluginManifestError, match="agent.tool"):
        PluginManifest.from_mapping(
            _manifest(capabilities=["desktop.overlay"]),
            source="test",
        )


def test_manifest_rejects_desktop_and_rpc_contracts_without_capabilities() -> None:
    with pytest.raises(PluginManifestError, match="plugin.rpc"):
        PluginManifest.from_mapping(
            _manifest(capabilities=["agent.tool", "desktop.overlay"]),
            source="test",
        )
    with pytest.raises(PluginManifestError, match="desktop.overlay"):
        PluginManifest.from_mapping(
            _manifest(capabilities=["agent.tool", "plugin.rpc"]),
            source="test",
        )
