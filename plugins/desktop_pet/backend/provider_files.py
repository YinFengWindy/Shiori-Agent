"""Native-selected files shared by explicitly dependent model providers."""

from pathlib import Path


def resolve_staged_zip(
    workspace: Path, source: str, *, namespace: str, max_bytes: int
) -> Path:
    """Require a bounded regular ZIP in one provider's native staging namespace."""
    requested = Path(source)
    if not requested.is_absolute() or ".." in requested.parts:
        raise ValueError("形象包必须来自原生文件选择")
    if not namespace or any(c in namespace for c in "/\\:") or namespace in {".", ".."}:
        raise ValueError("形象包暂存命名空间无效")
    staging = workspace.resolve() / "private_runtime" / "imports" / namespace
    canonical = requested.resolve(strict=True)
    if staging.resolve() != staging:
        raise ValueError("形象包暂存目录越界")
    if canonical != requested or not canonical.is_relative_to(staging):
        raise ValueError("形象包必须来自原生文件选择")
    if not canonical.is_file() or canonical.suffix.lower() != ".zip":
        raise ValueError("形象包必须是普通 ZIP 文件")
    if canonical.stat().st_size > max_bytes:
        raise ValueError(f"形象包超过 {max_bytes // (1024 * 1024)}MB")
    return canonical
