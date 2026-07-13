from pathlib import Path

from core.common.workspace import resolve_default_workspace


def test_resolve_default_workspace_uses_shiori_directory(tmp_path: Path) -> None:
    workspace = resolve_default_workspace(tmp_path)

    assert workspace == tmp_path / ".shiori" / "workspace"
    assert not workspace.exists()


def test_resolve_default_workspace_migrates_legacy_directory(tmp_path: Path) -> None:
    legacy_workspace = tmp_path / ".akashic" / "workspace"
    legacy_workspace.mkdir(parents=True)
    (legacy_workspace / "roles.json").write_text("{}", encoding="utf-8")

    workspace = resolve_default_workspace(tmp_path)

    assert workspace == tmp_path / ".shiori" / "workspace"
    assert (workspace / "roles.json").read_text(encoding="utf-8") == "{}"
    assert not legacy_workspace.exists()


def test_resolve_default_workspace_preserves_legacy_when_target_exists(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    workspace.mkdir(parents=True)
    legacy_workspace = tmp_path / ".akashic" / "workspace"
    legacy_workspace.mkdir(parents=True)

    assert resolve_default_workspace(tmp_path) == workspace
    assert workspace.exists()
    assert legacy_workspace.exists()
