"""Drift's ``read_file`` finds a skill's files in the drift directory first."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from plugins.proactive.backend.drift_tools import DriftReadFileTool


class _Host:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def file_tool_schema(self, name: str) -> Mapping[str, object]:
        return {"function": {"name": name, "parameters": {}}}

    async def run_drift_file_tool(
        self, role_id: str, name: str, arguments: Mapping[str, object]
    ) -> str:
        self.paths.append(str(arguments["path"]))
        return "ok"


@pytest.mark.parametrize("path", ["skills/meme/SKILL.md", "skills\\meme\\SKILL.md"])
async def test_a_skill_file_the_drift_directory_lacks_is_read_from_the_builtin(
    tmp_path: Path, path: str
) -> None:
    builtin = tmp_path / "builtin"
    (builtin / "meme").mkdir(parents=True)
    (builtin / "meme" / "SKILL.md").write_text("skill", encoding="utf-8")
    host = _Host()
    tool = DriftReadFileTool(host, "mira", tmp_path / "drift", builtin)  # type: ignore[arg-type]

    await tool.execute(path=path)

    assert host.paths == [str(builtin / "meme" / "SKILL.md")]


async def test_state_the_drift_directory_has_is_read_there(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    (builtin / "meme").mkdir(parents=True)
    (builtin / "meme" / "state.json").write_text("{}", encoding="utf-8")
    drift = tmp_path / "drift"
    (drift / "skills" / "meme").mkdir(parents=True)
    (drift / "skills" / "meme" / "state.json").write_text("{}", encoding="utf-8")
    host = _Host()
    tool = DriftReadFileTool(host, "mira", drift, builtin)  # type: ignore[arg-type]

    await tool.execute(path="skills/meme/state.json")

    assert host.paths == ["skills/meme/state.json"]
