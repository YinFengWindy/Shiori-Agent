"""Stage a verified runtime-only copy of a host-owned bundled plugin."""

import hashlib
from pathlib import Path

from agent.plugin_host.package_contract import validate_package
from agent.plugin_host.package_fingerprint import inspect_package_content


def stage_bundled_plugin(source: Path, stage: Path, plugin_id: str) -> dict[str, str]:
    """Copy manifest, backend and declared assets, then verify the exact copied bytes."""
    package = validate_package(source)
    if package.manifest.id != plugin_id:
        raise ValueError(f"随包插件身份不匹配: {plugin_id}")
    required = {"manifest.yaml", package.manifest.entry, *package.assets}
    required.update(
        name
        for name in {"README.md", "LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"}
        if (source / name).exists() or (source / name).is_symlink()
    )
    required.update(_backend_files(source / "backend", source))
    hashes: dict[str, str] = {}
    stage.mkdir(parents=True, exist_ok=False)
    for name in sorted(required):
        data = _read_source_file(source / name)
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    if inspect_package_content(stage).hashes != hashes:
        raise ValueError(f"随包插件内容在复制时变化: {plugin_id}")
    validate_package(stage)
    return hashes


def _backend_files(directory: Path, source: Path) -> set[str]:
    # Traverse only the published backend tree. A plugin's development venv,
    # tests and frontend dependencies are never inspected or copied.
    if directory.is_symlink() or directory.resolve() != directory.absolute():
        raise ValueError(f"随包插件源不能包含目录链接: {directory}")
    if not directory.is_dir():
        return set()
    selected: set[str] = set()
    for path in directory.iterdir():
        if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError(f"随包插件源不能包含链接: {path}")
        if path.is_dir():
            selected.update(_backend_files(path, source))
        else:
            selected.add(path.relative_to(source).as_posix())
    return selected


def _read_source_file(path: Path) -> bytes:
    if path.is_symlink() or path.resolve() != path.absolute() or not path.is_file():
        raise ValueError(f"随包插件源必须是无链接的普通文件: {path}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"随包插件内容在复制时变化: {path}")
    return data


def remove_bundled_stage(stage: Path, workspace: Path) -> None:
    """Remove only the host's staging directory, never an installed workspace package."""
    from desktop_bridge.runtime.plugin_package_store import remove_owned_directory

    owner = workspace.absolute() / "private_runtime" / "bundled-plugin-seeds"
    if not stage.absolute().is_relative_to(owner) or stage.absolute() == owner:
        raise ValueError("随包插件暂存目录越界")
    remove_owned_directory(stage.parent, stage.name)
