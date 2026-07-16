from __future__ import annotations

from pathlib import Path

import pytest

from agent.config import load_config


def _write_config(path: Path, extra: str = "") -> None:
    path.write_text(
        'provider = "openai"\n'
        'model = "test-model"\n'
        f"{extra}\n",
        encoding="utf-8",
    )


def test_coding_agents_are_disabled_for_legacy_config(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write_config(path)

    config = load_config(path)

    assert config.coding_agents.enabled is False
    assert config.coding_agents.profiles == {}


def test_loads_enabled_coding_agent_profiles_and_projects(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    worktrees = (tmp_path / "worktrees").as_posix()
    repository = (tmp_path / "repository").as_posix()
    _write_config(
        path,
        f'''
[coding_agents]
enabled = true
worktree_root = "{worktrees}"
default_project = "demo"
default_profile = "codex_default"
max_parallel_runs = 2

[coding_agents.profiles.codex_default]
provider = "codex"
model = "gpt-5.6"
effort = "high"
max_permission_level = "workspace-write"

[coding_agents.projects.demo]
repo_path = "{repository}"
max_parallel_runs = 2
''',
    )

    config = load_config(path)

    assert config.coding_agents.enabled is True
    assert config.coding_agents.default_profile == "codex_default"
    assert config.coding_agents.profiles["codex_default"].provider == "codex"
    assert config.coding_agents.projects["demo"].repo_path == repository


@pytest.mark.parametrize(
    "extra, message",
    [
        (
            '''
[coding_agents]
enabled = true
worktree_root = "relative"
default_profile = "codex_default"
[coding_agents.profiles.codex_default]
provider = "codex"
model = "gpt-5.6"
''',
            "worktree_root",
        ),
        (
            '''
[coding_agents]
enabled = true
worktree_root = "C:/worktrees"
default_profile = "bad"
[coding_agents.profiles.bad]
provider = "unknown"
model = "model"
''',
            "Provider",
        ),
    ],
)
def test_rejects_invalid_enabled_coding_agent_config(
    tmp_path: Path,
    extra: str,
    message: str,
) -> None:
    path = tmp_path / "config.toml"
    _write_config(path, extra)

    with pytest.raises(ValueError, match=message):
        load_config(path)
