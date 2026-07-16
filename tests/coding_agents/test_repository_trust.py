from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from coding_agents.repository_trust import (
    RepositoryApproval,
    RepositoryTrustError,
    RepositoryTrustScope,
    RepositoryTrustService,
    TrustedRepository,
    normalize_existing_directory,
)

_COMMIT = "a" * 40


class _FakeGit:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        call = list(args)
        self.calls.append(call)
        stdout = str(self.root) if "--show-toplevel" in call else f"{_COMMIT}\n"
        return subprocess.CompletedProcess(call, 0, stdout=stdout, stderr="")


def test_new_repository_path_requires_explicit_approval(tmp_path: Path):
    repository = tmp_path / "repo"
    nested = repository / "src"
    nested.mkdir(parents=True)
    git = _FakeGit(repository)

    resolution = RepositoryTrustService(git_runner=git).resolve(nested)

    assert resolution.requires_approval is True
    assert resolution.repository.root_path == repository
    assert resolution.repository.head_commit == _COMMIT
    assert git.calls[0] == [
        "git",
        "-C",
        str(nested),
        "rev-parse",
        "--show-toplevel",
    ]


def test_persistent_approval_registers_repository_name(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    git = _FakeGit(repository)
    service = RepositoryTrustService(git_runner=git)
    pending = service.resolve(repository)

    approved = service.approve(
        pending,
        RepositoryApproval(
            approval_id="approval-1",
            repository_id=pending.repository.repository_id,
            scope=RepositoryTrustScope.PERSISTENT,
        ),
    )
    resolved_again = service.resolve("repo")

    assert approved.requires_approval is False
    assert approved.trust_scope is RepositoryTrustScope.PERSISTENT
    assert resolved_again.requires_approval is False
    assert resolved_again.repository.repository_id == pending.repository.repository_id


def test_once_approval_does_not_persist_repository(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    service = RepositoryTrustService(git_runner=_FakeGit(repository))
    pending = service.resolve(repository)

    approved = service.approve(
        pending,
        RepositoryApproval(
            approval_id="approval-1",
            repository_id=pending.repository.repository_id,
            scope=RepositoryTrustScope.ONCE,
        ),
    )
    next_resolution = service.resolve(repository)

    assert approved.requires_approval is False
    assert approved.trust_scope is RepositoryTrustScope.ONCE
    assert next_resolution.requires_approval is True


def test_repository_approval_must_match_candidate_repository(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    service = RepositoryTrustService(git_runner=_FakeGit(repository))
    pending = service.resolve(repository)

    with pytest.raises(RepositoryTrustError) as error:
        service.approve(
            pending,
            RepositoryApproval(
                approval_id="approval-1",
                repository_id="different-repository",
                scope=RepositoryTrustScope.ONCE,
            ),
        )

    assert error.value.code == "repository_not_trusted"


def test_registered_repository_refreshes_head_without_new_approval(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    registered = TrustedRepository(
        repository_id="repo-1",
        name="example",
        root_path=repository,
        head_commit=_COMMIT,
    )
    service = RepositoryTrustService([registered], git_runner=_FakeGit(repository))

    resolution = service.resolve("repo-1")

    assert resolution.requires_approval is False
    assert resolution.repository.root_path == repository


def test_relative_and_parent_traversal_paths_are_rejected(tmp_path: Path):
    with pytest.raises(RepositoryTrustError) as relative_error:
        normalize_existing_directory("repo")
    with pytest.raises(RepositoryTrustError) as traversal_error:
        normalize_existing_directory(tmp_path / "repo" / "..")

    assert relative_error.value.code == "path_boundary_violation"
    assert traversal_error.value.code == "path_boundary_violation"


def test_symbolic_link_in_input_path_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    original = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == repository or original(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(RepositoryTrustError) as error:
        normalize_existing_directory(repository)

    assert error.value.code == "path_boundary_violation"


def test_git_root_must_contain_requested_path(tmp_path: Path):
    requested = tmp_path / "requested"
    unrelated = tmp_path / "unrelated"
    requested.mkdir()
    unrelated.mkdir()

    with pytest.raises(RepositoryTrustError) as error:
        RepositoryTrustService(git_runner=_FakeGit(unrelated)).resolve(requested)

    assert error.value.code == "path_boundary_violation"
