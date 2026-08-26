from pathlib import Path

from core.common.workspace import (
    resolve_default_workspace,
    resolve_ncatbot_dir,
)


def test_resolve_default_workspace_uses_shiori_directory(tmp_path: Path) -> None:
    workspace = resolve_default_workspace(tmp_path)

    assert workspace == tmp_path / ".shiori" / "workspace"
    assert not workspace.exists()


def test_resolve_ncatbot_dir_uses_shiori_directory(tmp_path: Path) -> None:
    assert resolve_ncatbot_dir(tmp_path) == tmp_path / ".shiori" / "ncatbot"
