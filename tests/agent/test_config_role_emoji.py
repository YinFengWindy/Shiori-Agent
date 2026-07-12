from pathlib import Path

import pytest

from agent.config import load_config


def _write_config(path: Path, entries: str) -> None:
    path.write_text(
        "\n".join(
            [
                'provider = "openai"',
                'model = "test"',
                "[agent.emoji]",
                f"entries = {entries}",
            ]
        ),
        encoding="utf-8",
    )


def test_load_config_parses_role_emoji_allowlist(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, '["heart=❤️", "smile=😊"]')

    config = load_config(config_path)

    assert config.role_emojis == {"heart": "❤️", "smile": "😊"}


def test_load_config_rejects_duplicate_role_emoji_names(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, '["heart=❤️", "heart=💗"]')

    with pytest.raises(ValueError, match="emoji 名称重复"):
        load_config(config_path)
