from __future__ import annotations

from pathlib import Path

import pytest

from agent.plugin_host.manifest import (
    ManifestError,
    declared_chat_types,
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
_PRIVATE = "{type: private, label: 私聊, chat_id_label: ID}"


def test_manifest_parses_static_channel_declarations(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST
        + "  - name: demo_chat\n    label: Demo\n    contact_label: 用户 ID\n"
        f"    chat_types: [{_PRIVATE}]\n"
        f"  - {{name: demo_group, label: Demo 群, chat_types: [{_PRIVATE}]}}\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    private = {
        "type": "private",
        "label": "私聊",
        "chat_id_label": "ID",
        "chat_id_hint": None,
        "prefix": None,
    }
    assert [item.to_dict() for item in manifest.channels] == [
        {
            "name": "demo_chat",
            "label": "Demo",
            "contact_label": "用户 ID",
            "chat_types": [private],
        },
        {
            "name": "demo_group",
            "label": "Demo 群",
            "contact_label": None,
            "chat_types": [private],
        },
    ]


def test_manifest_parses_channel_session_type_declarations(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST + "  - name: demo\n    label: Demo\n    chat_types:\n"
        "      - {type: private, label: 私聊, chat_id_label: 用户 ID}\n"
        "      - {type: group, label: 群聊, chat_id_label: 群号,"
        " chat_id_hint: 输入群号, prefix: 'g:'}\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    assert manifest.channels[0].to_dict()["chat_types"] == [
        {
            "type": "private",
            "label": "私聊",
            "chat_id_label": "用户 ID",
            "chat_id_hint": None,
            "prefix": None,
        },
        {
            "type": "group",
            "label": "群聊",
            "chat_id_label": "群号",
            "chat_id_hint": "输入群号",
            "prefix": "g:",
        },
    ]
    assert declared_chat_types([manifest]) == {"demo": manifest.channels[0].chat_types}


@pytest.mark.parametrize(
    "chat_types, message",
    [
        ("[]", "非空的会话类型列表"),
        ("private", "非空的会话类型列表"),
        ("null", "非空的会话类型列表"),
        ("[private]", r"chat_types\[0\] 必须是对象"),
        ("[{label: 私聊, chat_id_label: ID}]", "缺少 type"),
        ("[{type: private, chat_id_label: ID}]", "缺少 label"),
        ("[{type: private, label: 私聊}]", "缺少 chat_id_label"),
        ("[{type: channel, label: 频道, chat_id_label: ID}]", "private / group"),
        (f"[{_PRIVATE}, {_PRIVATE}]", "重复声明会话类型"),
        ("[{type: private, label: 私聊, chat_id_label: ID, icon: x}]", "未知字段"),
        ("[{type: private, label: 私聊, chat_id_label: ID, prefix: ''}]", "非空字符串"),
        ("[{type: private, label: 私聊, chat_id_label: ID, prefix: ' p:'}]", "空白"),
        (
            "[{type: private, label: 私聊, chat_id_label: ID, prefix: 'g'},"
            " {type: group, label: 群聊, chat_id_label: ID, prefix: 'gq:'}]",
            "前缀互相包含",
        ),
    ],
)
def test_manifest_rejects_invalid_session_type_declarations(
    tmp_path, chat_types, message
):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST
        + f"  - name: demo\n    label: Demo\n    chat_types: {chat_types}\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match=message):
        load_manifest(tmp_path)


def test_manifest_rejects_channel_without_session_types(tmp_path):
    # 每个渠道都必须声明会话类型，绑定面板和保存校验都依赖它。
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST + "  - {name: demo, label: Demo}\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="必须声明会话类型"):
        load_manifest(tmp_path)


@pytest.mark.parametrize("field", ["chat_id_label", "chat_id_hint"])
def test_manifest_rejects_channel_level_chat_id_copy(tmp_path, field):
    # 号码的标签与提示只由各会话类型给出。
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST + f"  - name: demo\n    label: Demo\n    {field}: 输入 ID\n"
        f"    chat_types: [{_PRIVATE}]\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="未知字段"):
        load_manifest(tmp_path)


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
        (
            f"  - {{name: demo, label: A, chat_types: [{_PRIVATE}]}}\n"
            f"  - {{name: demo, label: B, chat_types: [{_PRIVATE}]}}\n",
            "重复",
        ),
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


@pytest.mark.parametrize(
    "capabilities, declared, expected",
    [
        ("[config]", "", "feature"),
        ("[channels]", "", "channel"),
        ("[tool_hooks]", "category: system\n", "system"),
        ("[channels]", "category: feature\n", "feature"),
    ],
)
def test_manifest_category_defaults_from_capabilities(
    tmp_path, capabilities, declared, expected
):
    (tmp_path / "manifest.yaml").write_text(
        f"api: 2\ncapabilities: {capabilities}\n{declared}", encoding="utf-8"
    )
    assert load_manifest(tmp_path).category == expected


@pytest.mark.parametrize("value", ["internal", "3", "[system]"])
def test_manifest_rejects_unknown_category(tmp_path, value):
    (tmp_path / "manifest.yaml").write_text(
        f"api: 2\ncapabilities: []\ncategory: {value}\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="category"):
        load_manifest(tmp_path)


def test_builtin_channel_plugins_are_grouped_as_channels():
    root = Path(__file__).resolve().parents[4] / "plugins"
    manifests = [load_manifest(path.parent) for path in root.glob("*/manifest.yaml")]
    assert manifests
    for manifest in manifests:
        assert manifest is not None
        if "channels" in manifest.capabilities:
            assert manifest.category == "channel", manifest.id


def test_manifest_default_enabled_defaults_to_true(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: []\n", encoding="utf-8"
    )
    assert load_manifest(tmp_path).default_enabled is True


def test_manifest_accepts_default_enabled_false(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "api: 2\ncapabilities: []\ndefault_enabled: false\n", encoding="utf-8"
    )
    assert load_manifest(tmp_path).default_enabled is False


@pytest.mark.parametrize("value", ["'false'", "0", "[]", "null"])
def test_manifest_rejects_non_boolean_default_enabled(tmp_path, value):
    (tmp_path / "manifest.yaml").write_text(
        f"api: 2\ncapabilities: []\ndefault_enabled: {value}\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="default_enabled"):
        load_manifest(tmp_path)


def test_builtin_default_disabled_plugins_match_the_upgrade_migration():
    """manifest 里默认停用的内置插件必须登记在升级迁移里，否则升级用户会被悄悄停用。"""
    from agent.plugin_default_enabled_migration import DEFAULT_DISABLED_PLUGINS

    root = Path(__file__).resolve().parents[4] / "plugins"
    manifests = [load_manifest(path.parent) for path in root.glob("*/manifest.yaml")]
    default_disabled = {
        manifest.id
        for manifest in manifests
        if manifest and not manifest.default_enabled
    }
    assert default_disabled == set(DEFAULT_DISABLED_PLUGINS)
    assert default_disabled == {"browser_use", "computer_use"}


def test_manifest_looks_up_one_channel_session_types(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST
        + f"  - {{name: demo, label: Demo, chat_types: [{_PRIVATE}]}}\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None

    assert [item.type for item in manifest.channel_chat_types("demo")] == ["private"]
    with pytest.raises(KeyError, match="未声明渠道 other"):
        manifest.channel_chat_types("other")


def test_manifest_limits_dynamic_instances_to_declared_prefix(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        _CHANNEL_MANIFEST
        + f"  - {{name: demo, label: Demo, instance_prefix: demo_, chat_types: [{_PRIVATE}]}}\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest is not None
    assert manifest.channel_chat_types("demo_one") == manifest.channel_chat_types(
        "demo"
    )
    for name in ("demo_", "demo.unauthorized", "other_one"):
        with pytest.raises(KeyError):
            manifest.channel_chat_types(name)
    declarations = declared_chat_types([manifest])
    assert declarations.get("demo_one") == manifest.channels[0].chat_types
    assert declarations.get("demo_") is None
    assert declarations.get("demo.unauthorized") is None
    assert declarations.get("other_one") is None
