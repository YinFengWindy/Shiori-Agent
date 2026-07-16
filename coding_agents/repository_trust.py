from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

GitRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")


class RepositoryTrustError(ValueError):
    """仓库解析或信任校验失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RepositoryTrustScope(StrEnum):
    """一次性或持久化的仓库授权范围。"""

    ONCE = "once"
    PERSISTENT = "persistent"


@dataclass(frozen=True)
class TrustedRepository:
    """服务端已信任的仓库快照。"""

    repository_id: str
    name: str
    root_path: Path
    head_commit: str


@dataclass(frozen=True)
class RepositoryResolution:
    """一次候选仓库解析的确定性结果。"""

    repository: TrustedRepository
    requires_approval: bool
    trust_scope: RepositoryTrustScope | None = None


@dataclass(frozen=True)
class RepositoryApproval:
    """边界层签发并绑定到一个候选仓库的审批上下文。"""

    approval_id: str
    repository_id: str
    scope: RepositoryTrustScope | str


def normalize_existing_directory(path: str | Path) -> Path:
    """将不可信输入规范化为不存在重解析点的真实目录。"""
    raw_path = Path(path).expanduser()
    if not raw_path.is_absolute():
        raise RepositoryTrustError(
            "path_boundary_violation", "仓库路径必须是绝对路径"
        )
    if ".." in raw_path.parts:
        raise RepositoryTrustError(
            "path_boundary_violation", "仓库路径不能包含父目录跳转"
        )
    ensure_no_reparse_points(raw_path.absolute())
    try:
        resolved = raw_path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RepositoryTrustError("repository_not_found", "仓库路径不存在") from exc
    if not resolved.is_dir():
        raise RepositoryTrustError("repository_invalid", "仓库路径必须是目录")
    ensure_no_reparse_points(resolved)
    return resolved


def ensure_no_reparse_points(path: Path) -> None:
    """拒绝路径链上的符号链接和 Windows junction。"""
    current = path
    while True:
        try:
            is_junction = bool(getattr(current, "is_junction", lambda: False)())
            if current.is_symlink() or is_junction:
                raise RepositoryTrustError(
                    "path_boundary_violation", "仓库路径不能经过重解析点"
                )
        except OSError as exc:
            raise RepositoryTrustError(
                "repository_invalid", "无法安全检查仓库路径"
            ) from exc
        if current.parent == current:
            return
        current = current.parent


def paths_equal(left: Path, right: Path) -> bool:
    """按宿主机文件系统规则比较两个已规范化路径。"""
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def path_is_within(path: Path, parent: Path) -> bool:
    """按宿主机文件系统规则验证路径边界。"""
    normalized_path = os.path.normcase(str(path))
    normalized_parent = os.path.normcase(str(parent))
    try:
        return os.path.commonpath((normalized_path, normalized_parent)) == normalized_parent
    except ValueError:
        return False


class RepositoryTrustService:
    """解析对话仓库输入，并把首次路径转换为显式审批。"""

    def __init__(
        self,
        trusted_repositories: Iterable[TrustedRepository] = (),
        *,
        git_runner: GitRunner | None = None,
    ) -> None:
        self._git_runner = git_runner or _run_git
        self._repositories_by_id: dict[str, TrustedRepository] = {}
        self._repositories_by_name: dict[str, TrustedRepository] = {}
        self._repositories_by_path: dict[str, TrustedRepository] = {}
        for repository in trusted_repositories:
            self.register(repository)

    def register(self, repository: TrustedRepository) -> None:
        """注册由配置或持久化层加载的可信仓库。"""
        normalized = normalize_existing_directory(repository.root_path)
        canonical = TrustedRepository(
            repository_id=_required(repository.repository_id, "repository_id"),
            name=_required(repository.name, "name"),
            root_path=normalized,
            head_commit=_validate_commit(repository.head_commit),
        )
        path_key = _path_key(normalized)
        conflicts = (
            self._repositories_by_id.get(canonical.repository_id),
            self._repositories_by_name.get(canonical.name.casefold()),
            self._repositories_by_path.get(path_key),
        )
        if any(existing != canonical for existing in conflicts if existing is not None):
            raise RepositoryTrustError(
                "repository_invalid", "可信仓库 ID、名称或路径重复"
            )
        self._repositories_by_id[canonical.repository_id] = canonical
        self._repositories_by_name[canonical.name.casefold()] = canonical
        self._repositories_by_path[path_key] = canonical

    def resolve(self, candidate: str | Path) -> RepositoryResolution:
        """解析仓库 ID、名称或本地路径，不隐式授予首次路径权限。"""
        candidate_text = str(candidate).strip()
        if not candidate_text:
            raise RepositoryTrustError("repository_invalid", "仓库标识不能为空")
        registered = self._repositories_by_id.get(candidate_text)
        if registered is None:
            registered = self._repositories_by_name.get(candidate_text.casefold())
        if registered is not None:
            return RepositoryResolution(
                repository=self._refresh_registered(registered),
                requires_approval=False,
                trust_scope=RepositoryTrustScope.PERSISTENT,
            )

        requested_path = normalize_existing_directory(candidate_text)
        root_path = self._resolve_git_root(requested_path)
        registered = self._repositories_by_path.get(_path_key(root_path))
        if registered is not None:
            return RepositoryResolution(
                repository=self._refresh_registered(registered),
                requires_approval=False,
                trust_scope=RepositoryTrustScope.PERSISTENT,
            )
        repository = TrustedRepository(
            repository_id=_repository_id(root_path),
            name=root_path.name,
            root_path=root_path,
            head_commit=self._read_head(root_path),
        )
        return RepositoryResolution(repository=repository, requires_approval=True)

    def approve(
        self,
        resolution: RepositoryResolution,
        approval: RepositoryApproval,
    ) -> RepositoryResolution:
        """应用边界层已验证的仓库审批；持久授权同时进入当前注册表。"""
        if not resolution.requires_approval:
            return resolution
        if (
            not approval.approval_id.strip()
            or approval.repository_id != resolution.repository.repository_id
        ):
            raise RepositoryTrustError(
                "repository_not_trusted", "仓库审批与当前候选仓库不匹配"
            )
        try:
            scope = RepositoryTrustScope(approval.scope)
        except ValueError as exc:
            raise RepositoryTrustError(
                "repository_not_trusted", "仓库审批范围无效"
            ) from exc
        approved = RepositoryResolution(
            repository=resolution.repository,
            requires_approval=False,
            trust_scope=scope,
        )
        if scope is RepositoryTrustScope.PERSISTENT:
            self.register(resolution.repository)
        return approved

    def _refresh_registered(self, repository: TrustedRepository) -> TrustedRepository:
        root_path = normalize_existing_directory(repository.root_path)
        return TrustedRepository(
            repository_id=repository.repository_id,
            name=repository.name,
            root_path=root_path,
            head_commit=self._read_head(root_path),
        )

    def _resolve_git_root(self, requested_path: Path) -> Path:
        result = self._git(
            ["git", "-C", str(requested_path), "rev-parse", "--show-toplevel"]
        )
        root_text = result.stdout.strip()
        if not root_text:
            raise RepositoryTrustError("repository_invalid", "Git 未返回仓库根目录")
        root_path = normalize_existing_directory(root_text)
        if not path_is_within(requested_path, root_path):
            raise RepositoryTrustError(
                "path_boundary_violation", "Git 仓库根目录与请求路径不一致"
            )
        return root_path

    def _read_head(self, root_path: Path) -> str:
        result = self._git(
            ["git", "-C", str(root_path), "rev-parse", "--verify", "HEAD^{commit}"]
        )
        return _validate_commit(result.stdout.strip())

    def _git(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        result = self._git_runner(list(args))
        if result.returncode != 0:
            message = result.stderr.strip() or "Git 命令执行失败"
            raise RepositoryTrustError("repository_invalid", message)
        return result


def _run_git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _repository_id(root_path: Path) -> str:
    digest = hashlib.sha256(_path_key(root_path).encode("utf-8")).hexdigest()[:16]
    return f"repo-{digest}"


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path))


def _required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise RepositoryTrustError("repository_invalid", f"{field_name} 不能为空")
    return normalized


def _validate_commit(value: str) -> str:
    if not _GIT_COMMIT_PATTERN.fullmatch(value):
        raise RepositoryTrustError("repository_invalid", "Git commit 格式无效")
    return value.lower()
