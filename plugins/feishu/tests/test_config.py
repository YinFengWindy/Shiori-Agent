from __future__ import annotations

import pytest
from pydantic import ValidationError

from plugins.feishu.backend.config import FeishuConfigModel


def test_legacy_app_is_included_once_during_migration() -> None:
    config = FeishuConfigModel.model_validate(
        {
            "app_id": "cli_old",
            "app_secret": "old",
            "domain": "lark",
            "accounts": [
                {"app_id": "cli_new", "app_secret": "new", "domain": "feishu"}
            ],
        }
    )
    assert [(app.ref, app.app_secret) for app in config.applications] == [
        ("lark:cli_old", "old"),
        ("feishu:cli_new", "new"),
    ]


def test_config_model_normalizes_legacy_domains_and_rejects_others() -> None:
    legacy = FeishuConfigModel.model_validate(
        {"app_id": " a ", "app_secret": "s", "domain": "https://open.larksuite.com/"}
    )
    assert (legacy.app_id, legacy.domain) == ("a", "lark")
    assert legacy.base_url == "https://open.larksuite.com"
    assert FeishuConfigModel().base_url == "https://open.feishu.cn"
    with pytest.raises(ValidationError):
        FeishuConfigModel.model_validate({"domain": "open.example.com"})
    with pytest.raises(ValidationError):
        FeishuConfigModel.model_validate(
            {
                "accounts": [
                    {"app_id": "cli_a", "app_secret": "s", "domain": "lark"},
                    {"app_id": "cli_a", "app_secret": "s", "domain": "lark"},
                ]
            }
        )


def test_config_schema_renders_as_a_labelled_form() -> None:
    properties = FeishuConfigModel.model_json_schema()["properties"]
    assert list(properties) == ["app_id", "app_secret", "domain", "accounts"]
    assert properties["domain"]["enum"] == ["feishu", "lark"]
    assert all(item.get("title") for item in properties.values())
