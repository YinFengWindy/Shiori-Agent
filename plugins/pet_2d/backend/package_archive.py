"""Bounded data-only ZIP extraction and manifest integrity verification."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import stat
from typing import Any
import zipfile

from .validation import digest, number, object_value, package_path, read_json, text

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_ENTRIES = 2048
SCHEMA = "prelulu-avatar-package/v1"
_SUFFIXES = {".json", ".png", ".webp", ".psd"}


@dataclass(frozen=True)
class PackageManifest:
    """Verified package manifest and its immutable raw-byte identity."""

    document: dict[str, Any]
    sha256: str
    files: dict[str, dict[str, Any]]


def regular_path(root: Path, relative: str) -> Path:
    """Resolve one declared file without following a junction or symbolic link."""
    path = root / package_path(relative)
    if root.resolve() != root or path.resolve() != path or not path.is_file():
        raise ValueError(f"形象包文件越界或缺失: {relative}")
    return path


def file_sha256(path: Path) -> str:
    """Hash a file without loading the PSD or texture into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_manifest(root: Path) -> PackageManifest:
    """Read the exact supported manifest and bound every declared payload."""
    path = regular_path(root, "manifest.json")
    manifest = read_json(path, 2 * 1024 * 1024)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("不支持的形象包 schema")
    text(manifest.get("character"), "character", 200)
    text(manifest.get("version"), "version", 200)
    for key in ("name", "displayName", "display_name"):
        if key in manifest:
            text(manifest[key], key, 200)
    files = object_value(manifest.get("files"), "manifest.files")
    if not 1 <= len(files) <= MAX_ENTRIES:
        raise ValueError("形象包文件数量无效")
    seen: set[str] = set()
    total = 0
    for relative, raw in files.items():
        name = package_path(relative)
        if name == "manifest.json" or Path(name).suffix.lower() not in _SUFFIXES:
            raise ValueError(f"形象包包含不支持的文件: {name}")
        if name.casefold() in seen:
            raise ValueError("形象包清单包含重复路径")
        seen.add(name.casefold())
        entry = object_value(raw, f"files.{name}")
        total += int(
            number(entry.get("bytes"), name, low=0, high=MAX_FILE_BYTES, integer=True)
        )
        digest(entry.get("sha256"), name)
    if total > MAX_EXPANDED_BYTES:
        raise ValueError("形象包展开后超过大小限制")
    for key, expected in (("binding", "binding.json"), ("review", "review.json")):
        if manifest.get(key) != expected or expected not in files:
            raise ValueError(f"形象包 {key} 引用无效")
    for expected in (
        "rig/rig.json",
        "rig/baked.json",
        "editable/character.psd",
        "source.png",
    ):
        if expected not in files:
            raise ValueError(f"形象包缺少 {expected}")
    return PackageManifest(manifest, file_sha256(path), files)


def verify_files(root: Path, manifest: PackageManifest) -> None:
    """Revalidate installed bytes before preparation, including editable originals."""
    for relative, info in manifest.files.items():
        path = regular_path(root, relative)
        if path.stat().st_size != info["bytes"] or file_sha256(path) != info["sha256"]:
            raise ValueError(f"形象包完整性校验失败: {relative}")


def stage_archive(source: Path, destination: Path) -> PackageManifest:
    """Extract into a fresh private directory only after ZIP paths and bounds pass."""
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("形象包超过大小限制")
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES + 2:
            raise ValueError("形象包文件数量超过限制")
        names: dict[str, zipfile.ZipInfo] = {}
        seen: set[str] = set()
        total = 0
        for entry in entries:
            name = package_path(
                entry.orig_filename.removesuffix("/")
                if entry.is_dir()
                else entry.orig_filename
            )
            if name.casefold() in seen:
                raise ValueError("形象包 ZIP 包含重复路径")
            seen.add(name.casefold())
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR} or (entry.flag_bits & 1):
                raise ValueError("形象包不能包含链接、特殊文件或加密项")
            if entry.is_dir():
                continue
            if not 0 <= entry.file_size <= MAX_FILE_BYTES:
                raise ValueError("形象包文件超过大小限制")
            total += entry.file_size
            names[name] = entry
        if total > MAX_EXPANDED_BYTES:
            raise ValueError("形象包展开后超过大小限制")
        roots = [
            prefix for prefix in ("", "package/") if prefix + "manifest.json" in names
        ]
        if len(roots) != 1:
            raise ValueError("形象包必须包含唯一 manifest.json")
        prefix = roots[0]
        if any(not name.startswith(prefix) and name != "README.txt" for name in names):
            raise ValueError("形象包包含包目录外的文件")
        destination.mkdir(parents=True, exist_ok=False)
        manifest_entry = names[prefix + "manifest.json"]
        if manifest_entry.file_size > 2 * 1024 * 1024:
            raise ValueError("形象包清单超过大小限制")
        _copy_entry(
            archive,
            manifest_entry,
            destination / "manifest.json",
            manifest_entry.file_size,
        )
        manifest = read_manifest(destination)
        payload_names = {
            name.removeprefix(prefix) for name in names if name.startswith(prefix)
        } - {"manifest.json"}
        if not prefix:
            payload_names.discard("README.txt")
        if payload_names != set(manifest.files):
            raise ValueError("形象包清单与 ZIP 文件不一致")
        for relative, record in manifest.files.items():
            entry = names[prefix + relative]
            if entry.file_size != record["bytes"]:
                raise ValueError(f"形象包声明大小不一致: {relative}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            actual = _copy_entry(archive, entry, target, record["bytes"])
            if actual != record["sha256"]:
                raise ValueError(f"形象包完整性校验失败: {relative}")
        return manifest


def _copy_entry(
    archive: zipfile.ZipFile, entry: zipfile.ZipInfo, target: Path, limit: int
) -> str:
    result = hashlib.sha256()
    copied = 0
    with archive.open(entry) as source, target.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            copied += len(chunk)
            if copied > limit:
                raise ValueError("形象包实际展开大小超过声明")
            result.update(chunk)
            output.write(chunk)
    if copied != limit:
        raise ValueError("形象包实际展开大小与声明不一致")
    return result.hexdigest()
