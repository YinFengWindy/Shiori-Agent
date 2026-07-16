from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from coding_agents.repository_trust import (
    RepositoryTrustError,
    ensure_no_reparse_points,
    normalize_existing_directory,
    path_is_within,
    paths_equal,
)

GitRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")


class WorkspaceError(RuntimeError):
    """受管 worktree 操作失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WorkspaceRequest:
    """创建独立 worktree 所需的不可变输入。"""

    workspace_id: str
    run_id: str
    repository_id: str
    repository_path: Path
    base_ref: str = "HEAD"


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """已创建 worktree 的路径、分支和基线快照。"""

    workspace_id: str
    run_id: str
    repository_id: str
    repository_path: Path
    worktree_path: Path
    baseline_commit: str
    branch_name: str
    source_was_dirty: bool


class WorktreeManager:
    """在单一受管根目录下创建和检查 Git worktree。"""

    def __init__(
        self, worktree_root: str | Path, *, git_runner: GitRunner | None = None
    ) -> None:
        raw_root = Path(worktree_root).expanduser()
        if not raw_root.is_absolute():
            raise WorkspaceError(
                "path_boundary_violation", "worktree_root 必须是绝对路径"
            )
        _ensure_safe_path(raw_root.absolute())
        self.root = raw_root.resolve(strict=False)
        if self.root.exists():
            if not self.root.is_dir():
                raise WorkspaceError(
                    "path_boundary_violation", "worktree_root 必须是目录"
                )
        self._git_runner = git_runner or _run_git

    def workspace_path(self, repository_id: str, run_id: str) -> Path:
        """生成并验证 `<root>/<repository_id>/<run_id>` 路径。"""
        repository_segment = _validate_identifier(repository_id, "repository_id")
        run_segment = _validate_identifier(run_id, "run_id")
        target = (self.root / repository_segment / run_segment).resolve(strict=False)
        if not path_is_within(target, self.root) or paths_equal(target, self.root):
            raise WorkspaceError(
                "path_boundary_violation", "worktree 路径逃逸受管根目录"
            )
        return target

    def create(self, request: WorkspaceRequest) -> WorkspaceSnapshot:
        """从已提交基线创建新分支 worktree，保留失败现场。"""
        _ = _validate_identifier(request.workspace_id, "workspace_id")
        worktree_path = self.workspace_path(request.repository_id, request.run_id)
        repository_path = _normalize_repository(request.repository_path)
        if path_is_within(self.root, repository_path) or path_is_within(
            repository_path, self.root
        ):
            raise WorkspaceError(
                "path_boundary_violation", "worktree_root 与目标仓库不能互相包含"
            )
        if worktree_path.exists():
            raise WorkspaceError(
                "worktree_create_failed", "目标 worktree 路径已存在"
            )

        baseline_commit = self._resolve_baseline(repository_path, request.base_ref)
        source_was_dirty = bool(
            self._git(
                ["git", "-C", str(repository_path), "status", "--porcelain"]
            ).stdout.strip()
        )
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_safe_path(worktree_path.parent)
        branch_name = f"shiori/run-{request.run_id}"
        _ = self._git(
            [
                "git",
                "-C",
                str(repository_path),
                "worktree",
                "add",
                "-b",
                branch_name,
                str(worktree_path),
                baseline_commit,
            ],
            code="worktree_create_failed",
        )
        return WorkspaceSnapshot(
            workspace_id=request.workspace_id,
            run_id=request.run_id,
            repository_id=request.repository_id,
            repository_path=repository_path,
            worktree_path=worktree_path,
            baseline_commit=baseline_commit,
            branch_name=branch_name,
            source_was_dirty=source_was_dirty,
        )

    def list_worktrees(self, repository_path: str | Path) -> tuple[Path, ...]:
        """读取 Git 当前登记的所有 worktree 路径。"""
        repository = _normalize_repository(repository_path)
        output = self._git(
            ["git", "-C", str(repository), "worktree", "list", "--porcelain"]
        ).stdout
        paths: list[Path] = []
        for line in output.splitlines():
            if not line.startswith("worktree "):
                continue
            paths.append(Path(line.removeprefix("worktree ")).resolve(strict=False))
        return tuple(paths)

    def adopt_existing(self, request: WorkspaceRequest) -> WorkspaceSnapshot:
        """Recover a deterministic worktree created before its DB mapping committed."""

        expected = self.validate_cleanup_target(
            request.repository_id,
            request.run_id,
            self.workspace_path(request.repository_id, request.run_id),
        )
        repository = _normalize_repository(request.repository_path)
        if not expected.is_dir() or not any(
            paths_equal(expected, path) for path in self.list_worktrees(repository)
        ):
            raise WorkspaceError(
                "worktree_create_failed",
                "现有路径不是目标仓库登记的受管 worktree",
            )
        baseline = self._git(
            ["git", "-C", str(expected), "rev-parse", "--verify", "HEAD^{commit}"]
        ).stdout.strip()
        if not _COMMIT_PATTERN.fullmatch(baseline):
            raise WorkspaceError("worktree_create_failed", "现有 worktree HEAD 无效")
        branch_name = self._git(
            ["git", "-C", str(expected), "branch", "--show-current"]
        ).stdout.strip()
        expected_branch = f"shiori/run-{request.run_id}"
        if branch_name != expected_branch:
            raise WorkspaceError("worktree_create_failed", "现有 worktree 分支不匹配")
        return WorkspaceSnapshot(
            workspace_id=request.workspace_id,
            run_id=request.run_id,
            repository_id=request.repository_id,
            repository_path=repository,
            worktree_path=expected,
            baseline_commit=baseline.lower(),
            branch_name=branch_name,
            source_was_dirty=False,
        )

    def find_orphans(
        self,
        repository_path: str | Path,
        known_worktree_paths: Iterable[str | Path],
    ) -> tuple[Path, ...]:
        """列出位于受管根内但没有持久化映射的 Git worktree。"""
        known = tuple(Path(path).resolve(strict=False) for path in known_worktree_paths)
        return tuple(
            path
            for path in self.list_worktrees(repository_path)
            if path_is_within(path, self.root)
            and not any(paths_equal(path, mapped) for mapped in known)
        )

    def validate_cleanup_target(
        self, repository_id: str, run_id: str, candidate: str | Path
    ) -> Path:
        """删除前重新验证候选路径正是受管 Run worktree。"""
        expected = self.workspace_path(repository_id, run_id)
        raw_candidate = Path(candidate).expanduser()
        _ensure_safe_path(raw_candidate.absolute())
        resolved = raw_candidate.resolve(strict=False)
        if not paths_equal(resolved, expected):
            raise WorkspaceError(
                "path_boundary_violation", "清理目标不是指定 Run 的 worktree"
            )
        if resolved.exists():
            _ensure_safe_path(resolved)
        return resolved

    def _resolve_baseline(self, repository_path: Path, base_ref: str) -> str:
        normalized_ref = base_ref.strip()
        if not normalized_ref or normalized_ref.startswith("-"):
            raise WorkspaceError("worktree_create_failed", "base_ref 无效")
        result = self._git(
            [
                "git",
                "-C",
                str(repository_path),
                "rev-parse",
                "--verify",
                f"{normalized_ref}^{{commit}}",
            ],
            code="worktree_create_failed",
        )
        commit = result.stdout.strip()
        if not _COMMIT_PATTERN.fullmatch(commit):
            raise WorkspaceError("worktree_create_failed", "Git 基线 commit 格式无效")
        return commit.lower()

    def _git(
        self, args: Sequence[str], *, code: str = "worktree_create_failed"
    ) -> subprocess.CompletedProcess[str]:
        result = self._git_runner(list(args))
        if result.returncode != 0:
            raise WorkspaceError(code, result.stderr.strip() or "Git 命令执行失败")
        return result


def _normalize_repository(path: str | Path) -> Path:
    try:
        return normalize_existing_directory(path)
    except RepositoryTrustError as exc:
        raise WorkspaceError(exc.code, str(exc)) from exc


def _ensure_safe_path(path: Path) -> None:
    try:
        ensure_no_reparse_points(path)
    except RepositoryTrustError as exc:
        raise WorkspaceError(exc.code, str(exc)) from exc


def _validate_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise WorkspaceError(
            "path_boundary_violation", f"{field_name} 不能用于受管路径"
        )
    return normalized


def _run_git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
