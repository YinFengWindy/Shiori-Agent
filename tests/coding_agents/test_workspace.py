from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from coding_agents.workspace import (
    WorkspaceError,
    WorkspaceRequest,
    WorktreeManager,
)

_COMMIT = "b" * 40


class _FakeGit:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail_worktree = False
        self.worktree_listing = ""

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        call = list(args)
        self.calls.append(call)
        if "rev-parse" in call:
            return subprocess.CompletedProcess(call, 0, stdout=_COMMIT, stderr="")
        if "status" in call:
            return subprocess.CompletedProcess(call, 0, stdout=" M tracked.py\n", stderr="")
        if call[-2:] == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(
                call, 0, stdout="shiori/run-run-1\n", stderr=""
            )
        if call[-2:] == ["list", "--porcelain"]:
            return subprocess.CompletedProcess(
                call, 0, stdout=self.worktree_listing, stderr=""
            )
        if "add" in call and self.fail_worktree:
            Path(call[-2]).mkdir(parents=True)
            return subprocess.CompletedProcess(call, 1, stdout="", stderr="add failed")
        return subprocess.CompletedProcess(call, 0, stdout="", stderr="")


def _request(repository: Path, *, run_id: str = "run-1") -> WorkspaceRequest:
    return WorkspaceRequest(
        workspace_id=f"workspace-{run_id}",
        run_id=run_id,
        repository_id="repo-1",
        repository_path=repository,
    )


def test_create_uses_distinct_managed_path_and_git_argument_array(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    managed_root = tmp_path / "managed"
    git = _FakeGit()
    manager = WorktreeManager(managed_root, git_runner=git)

    snapshot = manager.create(_request(repository))

    assert snapshot.worktree_path == managed_root / "repo-1" / "run-1"
    assert snapshot.branch_name == "shiori/run-run-1"
    assert snapshot.baseline_commit == _COMMIT
    assert snapshot.source_was_dirty is True
    assert git.calls[-1] == [
        "git",
        "-C",
        str(repository),
        "worktree",
        "add",
        "-b",
        "shiori/run-run-1",
        str(snapshot.worktree_path),
        _COMMIT,
    ]


def test_parallel_runs_receive_different_worktree_paths(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    manager = WorktreeManager(tmp_path / "managed", git_runner=_FakeGit())

    first = manager.create(_request(repository, run_id="run-1"))
    second = manager.create(_request(repository, run_id="run-2"))

    assert first.worktree_path != second.worktree_path


def test_identifier_traversal_is_rejected_before_git_runs(tmp_path: Path):
    git = _FakeGit()
    manager = WorktreeManager(tmp_path / "managed", git_runner=git)

    with pytest.raises(WorkspaceError) as error:
        manager.workspace_path("repo-1", "../outside")

    assert error.value.code == "path_boundary_violation"
    assert git.calls == []


def test_relative_managed_root_is_rejected():
    with pytest.raises(WorkspaceError) as error:
        WorktreeManager("relative/worktrees")

    assert error.value.code == "path_boundary_violation"


def test_managed_root_rejects_reparse_point_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    reparse_parent = tmp_path / "junction"
    original = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == reparse_parent or original(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(WorkspaceError) as error:
        WorktreeManager(reparse_parent / "managed")

    assert error.value.code == "path_boundary_violation"


def test_managed_root_inside_repository_is_rejected_on_create(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    manager = WorktreeManager(repository / ".worktrees", git_runner=_FakeGit())

    with pytest.raises(WorkspaceError) as error:
        manager.create(_request(repository))

    assert error.value.code == "path_boundary_violation"


def test_repository_inside_managed_root_is_rejected_on_create(tmp_path: Path):
    managed_root = tmp_path / "managed"
    repository = managed_root / "repositories" / "repo"
    repository.mkdir(parents=True)
    manager = WorktreeManager(managed_root, git_runner=_FakeGit())

    with pytest.raises(WorkspaceError) as error:
        manager.create(_request(repository))

    assert error.value.code == "path_boundary_violation"


def test_failed_git_add_preserves_partial_worktree_for_diagnosis(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    git = _FakeGit()
    git.fail_worktree = True
    manager = WorktreeManager(tmp_path / "managed", git_runner=git)
    expected = manager.workspace_path("repo-1", "run-1")

    with pytest.raises(WorkspaceError) as error:
        manager.create(_request(repository))

    assert error.value.code == "worktree_create_failed"
    assert expected.exists()


def test_adopt_existing_requires_registered_matching_worktree(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    managed_root = tmp_path / "managed"
    git = _FakeGit()
    manager = WorktreeManager(managed_root, git_runner=git)
    expected = manager.workspace_path("repo-1", "run-1")
    expected.mkdir(parents=True)
    git.worktree_listing = f"worktree {expected}\nHEAD {_COMMIT}\n"

    snapshot = manager.adopt_existing(_request(repository))

    assert snapshot.worktree_path == expected
    assert snapshot.baseline_commit == _COMMIT
    assert snapshot.branch_name == "shiori/run-run-1"


def test_find_orphans_only_returns_unmapped_managed_worktrees(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    managed_root = tmp_path / "managed"
    known = managed_root / "repo-1" / "known"
    orphan = managed_root / "repo-1" / "orphan"
    outside = tmp_path / "outside"
    git = _FakeGit()
    git.worktree_listing = (
        f"worktree {repository}\nHEAD {_COMMIT}\n\n"
        f"worktree {known}\nHEAD {_COMMIT}\n\n"
        f"worktree {orphan}\nHEAD {_COMMIT}\n\n"
        f"worktree {outside}\nHEAD {_COMMIT}\n"
    )
    manager = WorktreeManager(managed_root, git_runner=git)

    result = manager.find_orphans(repository, [known])

    assert result == (orphan,)


def test_cleanup_target_must_exactly_match_run_path(tmp_path: Path):
    manager = WorktreeManager(tmp_path / "managed", git_runner=_FakeGit())

    with pytest.raises(WorkspaceError) as error:
        manager.validate_cleanup_target("repo-1", "run-1", tmp_path)

    assert error.value.code == "path_boundary_violation"


def test_cleanup_target_rejects_reparse_point_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = WorktreeManager(tmp_path / "managed", git_runner=_FakeGit())
    candidate = manager.workspace_path("repo-1", "run-1")
    candidate.mkdir(parents=True)
    original = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == candidate or original(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(WorkspaceError) as error:
        manager.validate_cleanup_target("repo-1", "run-1", candidate)

    assert error.value.code == "path_boundary_violation"
