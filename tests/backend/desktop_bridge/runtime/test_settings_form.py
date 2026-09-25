"""Settings-form derivation preserves current plugin TOML values."""

import tomllib
import pytest
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.settings_form import settings_form_write


@pytest.mark.parametrize(
    "plugins",
    [
        'plugins."unknown.id" = { items = [{ "quoted.key" = { "space key" = [1, 2] } }, 1] }\n',
        '[plugins.qqbot]\napp_id = "app"\nclient_secret = "secret"\nenabled = false\n',
        'plugins."unknown.id" = { items = [{ name = "x", ports = [1, 2] }], enabled = true }\n',
        '[plugins.demo]\nlabels = ["a", "b"]\n[plugins.demo.nested]\nlimit = 3\n[[plugins.demo.routes]]\nname = "first"\n[plugins.demo.routes.options]\nactive = true\n',
    ],
)
def test_form_preserves_plugin_values_and_retains_ordinary_candidate_semantics(plugins):
    current = plugins + "\n[agent]\nmax_tokens = 100\n[voice]\nenabled = true\n"
    candidate = "[agent]\nmax_tokens = 200\n"
    derive = settings_form_write({"config_toml": candidate, "preserve_plugins": True})
    assert derive is not None
    result = tomllib.loads(derive.build_config_toml(current))
    assert result == {
        "agent": {"max_tokens": 200},
        "plugins": tomllib.loads(current)["plugins"],
    }
    assert derive.fingerprint_payload["config_toml"] == candidate


def test_form_preserves_host_migration_receipts():
    """普通设置保存不能丢掉迁移回执，否则一次性迁移会在下次启动时重跑。"""
    current = (
        "[agent]\nmax_tokens = 100\n"
        '[_migrations]\nplugin_default_disabled = ["browser_use", "computer_use"]\n'
    )
    derive = settings_form_write(
        {"config_toml": "[agent]\nmax_tokens = 200\n", "preserve_plugins": True}
    )
    assert derive is not None
    result = tomllib.loads(derive.build_config_toml(current))
    assert result == {
        "agent": {"max_tokens": 200},
        "_migrations": {"plugin_default_disabled": ["browser_use", "computer_use"]},
    }


def test_raw_apply_keeps_full_document_ownership():
    assert (
        settings_form_write({"config_toml": "[plugins.demo]\nenabled = false\n"})
        is None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"preserve_plugins": "yes"},
        {"preserve_plugins": True},
        {"preserve_plugins": True, "config_toml": "not valid TOML"},
        {"preserve_plugins": True, "config_toml": "[plugins.demo]\nenabled = true\n"},
        {"preserve_plugins": True, "config_toml": "[_migrations]\nreceipt = []\n"},
    ],
)
def test_ambiguous_or_invalid_form_draft_is_rejected(payload):
    with pytest.raises(RuntimeApplyError):
        settings_form_write(payload)
