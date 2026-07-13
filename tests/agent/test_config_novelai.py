from __future__ import annotations

from pathlib import Path

from agent.config import load_config


def test_load_config_reads_novelai_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "openai"

[llm.main]
model = "gpt-4.1"
api_key = "sk-test"
base_url = "https://api.openai.com/v1"

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
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.novelai.enabled is True
    assert config.novelai.token == "novel-token"
    assert config.novelai.base_url == "https://image.novelai.net"
    assert config.novelai.default_model == "nai-diffusion-4-5-curated"
    assert config.novelai.nsfw_model == "nai-diffusion-4-5-full"
    assert config.novelai.nsfw_enabled is True
    assert config.novelai.add_quality_tags is True
    assert config.novelai.undesired_content_preset == 2
    assert config.novelai.allow_txt2img is True
    assert config.novelai.allow_img2img is False
    assert config.novelai.auto_writeback_role_assets is True
    assert config.novelai.max_pixels == 524288
    assert config.novelai.max_steps == 20


def test_load_config_disables_proactive_when_role_id_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "openai"

[llm.main]
model = "gpt-4.1"
api_key = "sk-test"
base_url = "https://api.openai.com/v1"

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

    assert config.proactive.enabled is False


def test_load_config_keeps_channel_permissions_in_role_bindings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "openai"

[llm.main]
model = "gpt-4.1"
api_key = "sk-test"
base_url = "https://api.openai.com/v1"

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

    assert config.channels.telegram is not None
    assert config.channels.qq is not None
    assert not hasattr(config.channels.telegram, "allow_from")
    assert not hasattr(config.channels.qq, "allow_from")
    assert not hasattr(config.channels.qq, "groups")
