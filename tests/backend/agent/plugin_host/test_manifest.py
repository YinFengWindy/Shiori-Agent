from __future__ import annotations

from pathlib import Path

import pytest

from agent.plugin_host.manifest import (
    ManifestError,
    load_manifest,
)


def test_missing_manifest_returns_none(tmp_path: Path):
    assert load_manifest(tmp_path) is None


def test_display_name_does_not_replace_stable_plugin_identity(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\nid: screen_perception\ndisplay_name: 24h视奸插件\ncapabilities: []\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    assert manifest.id == "screen_perception"
    assert manifest.display_name == "24h视奸插件"


@pytest.mark.parametrize("content", [b"api: 2\ncapabilities: [\n", b"\xff"])
def test_manifest_wraps_invalid_yaml_and_encoding(tmp_path, content):
    (tmp_path / "manifest.yaml").write_bytes(content)
    with pytest.raises(ManifestError, match="manifest.yaml") as caught:
        load_manifest(tmp_path)
    assert caught.value.__cause__ is not None


def test_manifest_wraps_read_failure(tmp_path, monkeypatch):
    (tmp_path / "manifest.yaml").write_text("api: 2\n", encoding="utf-8")

    def deny_read(*args, **kwargs):
        raise PermissionError("manifest access denied")

    monkeypatch.setattr(Path, "read_text", deny_read)
    with pytest.raises(ManifestError, match="manifest.yaml") as caught:
        load_manifest(tmp_path)
    assert isinstance(caught.value.__cause__, PermissionError)


@pytest.mark.parametrize(
    "api", ["", "api: 1\n", "api: 3\n", "api: true\n", "api: '2'\n"]
)
def test_manifest_requires_explicit_supported_api(tmp_path: Path, api: str):
    (tmp_path / "manifest.yaml").write_text(
        api + "id: demo\ncapabilities: []\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="api: 2"):
        load_manifest(tmp_path)


def test_v2_manifest_parses_capabilities(tmp_path: Path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\nid: demo\nversion: '0.1'\nentry: main.py\n"
        "capabilities:\n  - events\n  - kv\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    assert manifest.api == 2
    assert manifest.entry == "main.py"
    assert manifest.capabilities == ("events", "kv")


def test_v2_manifest_requires_capabilities(tmp_path: Path):
    (tmp_path / "manifest.yaml").write_text("api: 2\nid: demo\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="capabilities"):
        _ = load_manifest(tmp_path)


def test_unknown_capability_rejected(tmp_path: Path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities:\n  - warp_drive\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="warp_drive"):
        _ = load_manifest(tmp_path)


def test_manifest_parses_optional_dependencies_without_making_them_strong(
    tmp_path: Path,
):
    _ = (tmp_path / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: [dependencies]\n"
        "optional_dependencies: [observe, observe]\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    assert manifest.optional_dependencies == ("observe",)
    assert manifest.dependencies == ()


@pytest.mark.parametrize("value", ["observe", "[null]", "['']", "[3]"])
def test_manifest_rejects_invalid_optional_dependency_ids(tmp_path: Path, value: str):
    _ = (tmp_path / "manifest.yaml").write_text(
        f"api: 2\ncapabilities: []\noptional_dependencies: {value}\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="optional_dependencies"):
        load_manifest(tmp_path)


def test_dependency_cannot_be_both_strong_and_optional(tmp_path: Path):
    _ = (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: []\ndependencies: [observe]\n"
        "optional_dependencies: [observe]\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="同时声明"):
        load_manifest(tmp_path)


@pytest.mark.parametrize("value", ["false", "true"])
def test_manifest_declares_hot_unload_support(tmp_path, value):
    (tmp_path / "manifest.yaml").write_text(
        f"api: 2\ncapabilities: []\nsupports_hot_unload: {value}\n", encoding="utf-8"
    )
    assert load_manifest(tmp_path).supports_hot_unload is (value == "true")


@pytest.mark.parametrize("value", ["'false'", "0", "[]", "null"])
def test_manifest_rejects_non_boolean_hot_unload_declaration(tmp_path, value):
    (tmp_path / "manifest.yaml").write_text(
        f"api: 2\ncapabilities: []\nsupports_hot_unload: {value}\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="supports_hot_unload"):
        load_manifest(tmp_path)


def test_existing_manifest_defaults_to_hot_unloadable(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: []\n", encoding="utf-8"
    )
    assert load_manifest(tmp_path).supports_hot_unload is True


def test_manifest_rejects_nonstring_keys(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: []\n3: value\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="keys must be strings"):
        load_manifest(tmp_path)


_CHANNEL_MANIFEST = "api: 2\nid: demo\ncapabilities: [channels]\nchannels:\n"


def test_manifest_parses_static_channel_declarations(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST
        + "  - name: demo_chat\n    label: Demo\n    contact_label: 用户 ID\n"
        "    chat_id_label: 私聊 chat_id\n    chat_id_hint: dm:<用户 ID>\n"
        "  - {name: demo_group, label: Demo 群}\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    assert [item.to_dict() for item in manifest.channels] == [
        {
            "name": "demo_chat",
            "label": "Demo",
            "contact_label": "用户 ID",
            "chat_id_label": "私聊 chat_id",
            "chat_id_hint": "dm:<用户 ID>",
        },
        {
            "name": "demo_group",
            "label": "Demo 群",
            "contact_label": None,
            "chat_id_label": None,
            "chat_id_hint": None,
        },
    ]


def test_manifest_without_channels_declares_none(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: [channels]\n", encoding="utf-8"
    )
    assert load_manifest(tmp_path).channels == ()


@pytest.mark.parametrize(
    "declarations, message",
    [
        ("  demo\n", "列表"),
        ("  - demo\n", r"channels\[0\] 必须是对象"),
        ("  - {label: Demo}\n", "缺少 name"),
        ("  - {name: demo}\n", "缺少 label"),
        ("  - {name: demo, label: ''}\n", "非空字符串"),
        ("  - {name: demo, label: 3}\n", "非空字符串"),
        ("  - {name: Demo, label: Demo}\n", "小写"),
        ("  - {name: desktop, label: 桌面}\n", "保留"),
        ("  - {name: demo, label: Demo, icon: x}\n", "未知字段"),
        ("  - {name: demo, label: A}\n  - {name: demo, label: B}\n", "重复"),
    ],
)
def test_manifest_rejects_invalid_channel_declarations(tmp_path, declarations, message):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST + declarations, encoding="utf-8"
    )
    with pytest.raises(ManifestError, match=message):
        load_manifest(tmp_path)


def test_channel_declarations_require_channels_capability(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: [config]\nchannels:\n  - {name: demo, label: Demo}\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="capabilities"):
        load_manifest(tmp_path)
