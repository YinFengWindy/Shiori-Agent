"""Path normalization without host configuration or implicit workspace."""

from pathlib import Path


def resolve_path(path: str, allowed_dir: Path | None = None) -> Path:
    """解析路径（展开 ~ 并取绝对路径），可选限制在允许目录内。

    相对路径规则：
    - 若提供了 allowed_dir，相对路径基于 allowed_dir 解析（工作目录为 allowed_dir）
    - 否则相对路径基于进程 cwd 解析
    """
    p = Path(path).expanduser()
    if not p.is_absolute() and allowed_dir is not None:
        resolved = (allowed_dir / p).resolve()
    else:
        resolved = p.resolve()
    if allowed_dir is not None:
        allowed_root = allowed_dir.resolve()
        try:
            resolved.relative_to(allowed_root)
        except ValueError as exc:
            raise PermissionError(f"路径 {path} 超出允许目录 {allowed_dir}") from exc
    return resolved
