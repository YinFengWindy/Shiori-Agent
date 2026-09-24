from __future__ import annotations

import tomllib
from pathlib import Path

from agent.config import load_config


def _base_toml(extra: str) -> str:
    return ("""
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "gpt-4.1"
api_key = "sk-test"
base_url = "https://api.openai.com/v1"
effort = "none"
""" + extra).strip()


def test_config_no_longer_carries_a_dedicated_novelai_field(tmp_path: Path) -> None:
    """Issue #180: novelai settings live entirely under ``config.plugins["novelai"]`` now."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(_base_toml(""), encoding="utf-8")

    config = load_config(config_path)

    assert not hasattr(config, "novelai")


def test_load_config_migrates_legacy_integrations_novelai_into_plugins_table(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _base_toml("""
[integrations.novelai]
enabled = true
token = "novel-token"
base_url = "https://image.novelai.net"
default_model = "nai-diffusion-4-5-curated"
nsfw_model = "nai-diffusion-4-5-full"
nsfw_enabled = true
add_quality_tags = true
undesired_content_preset = 2
allow_txt2img = true
allow_img2img = false
auto_writeback_role_assets = true
max_pixels = 524288
max_steps = 20
default_samples = 1
"""),
        encoding="utf-8",
    )

    config = load_config(config_path)

    settings = config.plugins["novelai"]
    assert settings["enabled"] is True
    assert settings["token"] == "novel-token"
    assert settings["base_url"] == "https://image.novelai.net"
    assert settings["default_model"] == "nai-diffusion-4-5-curated"
    assert settings["nsfw_model"] == "nai-diffusion-4-5-full"
    assert settings["nsfw_enabled"] is True
    assert settings["add_quality_tags"] is True
    assert settings["undesired_content_preset"] == 2
    assert settings["allow_txt2img"] is True
    assert settings["allow_img2img"] is False
    assert settings["auto_writeback_role_assets"] is True
    assert settings["max_pixels"] == 524288
    assert settings["max_steps"] == 20

    # The migration is one-way: the legacy table is gone from the persisted
    # file, and the values now live under [plugins.novelai] instead.
    migrated_text = config_path.read_text(encoding="utf-8")
    migrated_document = tomllib.loads(migrated_text)
    assert "novelai" not in migrated_document.get("integrations", {})
    assert migrated_document["plugins"]["novelai"]["token"] == "novel-token"


def test_migration_is_idempotent_across_repeated_loads(tmp_path: Path) -> None:
    """Running the migration twice must not error, duplicate, or drop data."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _base_toml("""
[integrations.novelai]
enabled = true
token = "novel-token"
"""),
        encoding="utf-8",
    )

    first = load_config(config_path)
    text_after_first = config_path.read_text(encoding="utf-8")
    second = load_config(config_path)
    text_after_second = config_path.read_text(encoding="utf-8")

    assert first.plugins["novelai"]["token"] == "novel-token"
    assert second.plugins["novelai"]["token"] == "novel-token"
    # Nothing left to migrate on the second load: the file is untouched.
    assert text_after_second == text_after_first


def test_migration_preserves_a_previously_stored_enabled_flag(tmp_path: Path) -> None:
    """[plugins.novelai].enabled can already exist (plugin management toggle)

    predating this migration — the migration must not clobber it with a
    value implied by the legacy table (which never had an ``enabled`` key
    under that name for this purpose before #180).
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _base_toml("""
[plugins.novelai]
enabled = false

[integrations.novelai]
enabled = true
token = "novel-token"
"""),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.plugins["novelai"]["enabled"] is False
    assert config.plugins["novelai"]["token"] == "novel-token"


def test_migration_does_not_disturb_unrelated_config_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        _base_toml("""
[integrations.novelai]
enabled = true
token = "novel-token"

[agent]
max_tokens = 4096
"""),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.max_tokens == 4096


def test_load_config_preserves_proactive_base_config_without_role_target(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "gpt-4.1"
api_key = "sk-test"
base_url = "https://api.openai.com/v1"
effort = "none"

[proactive]
enabled = true
profile = "daily"

[proactive.target]
channel = "telegram"
chat_id = "1"
role_id = ""
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.proactive.enabled is True
    assert config.proactive.default_role_id == ""


def test_load_config_keeps_channel_permissions_in_role_bindings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "gpt-4.1"
api_key = "sk-test"
base_url = "https://api.openai.com/v1"
effort = "none"

[channels.telegram]
token = "telegram-token"
allow_from = ["legacy-user"]

[channels.qq]
bot_uin = "10001"
allow_from = ["legacy-user"]

[[channels.qq.groups]]
group_id = "123"
allow_from = ["legacy-user"]
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    # 旧的 allow_from / groups 不随渠道迁入插件表；白名单只看角色绑定。
    assert config.plugins["telegram"] == {"token": "telegram-token"}
    assert config.plugins["qq"] == {"bot_uin": "10001"}
