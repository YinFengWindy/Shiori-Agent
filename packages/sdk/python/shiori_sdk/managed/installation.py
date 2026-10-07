"""Immutable version directories and an atomically published current pointer."""

import shutil
import hashlib
import re
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import uuid4

from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.files.lease import LeaseBusy, exclusive_file_lease

from .artifacts import Artifact
from .acquisition import acquire_resources
from .paths import environment_path, native_path

GIB = 1024**3
# Reserve 5% of the estimate, at least 1 GiB, for logs, child temp/cache files
# and filesystem overhead that a fixed artifact list cannot enumerate.
SPACE_MARGIN_RATIO = 0.05
SPACE_MARGIN_MIN = GIB
# Removal keeps only lock and log files: other generations may hold the locks,
# and the logs explain a removal or a previous failure.
_RETAINED = frozenset({"prepare.lock", "service.lock", "prepare.log", "service.log"})


def required_space(missing: int, installed_size: int) -> int:
    """Bytes a preparation may add at its peak: missing artifacts, result and margin."""
    estimate = missing + installed_size
    return estimate + max(SPACE_MARGIN_MIN, int(estimate * SPACE_MARGIN_RATIO))


class Installation:
    """A failed or cancelled preparation never changes the previous usable version.

    ``installed_size`` is the provider-declared size in bytes of one prepared
    version (extracted archives, built environment); together with the missing
    artifact bytes it bounds the free-space check made before any copy.
    """

    def __init__(
        self,
        root: Path,
        revision: str,
        artifacts: Sequence[Artifact],
        *,
        installed_size: int = 0,
    ):
        if installed_size < 0:
            raise ValueError("安装大小不能为负数")
        self.root, self.revision, self.artifacts = (
            native_path(root),
            revision,
            tuple(artifacts),
        )
        self.installed_size = installed_size
        self.pointer = self.root / "current.json"

    def current(self) -> Path | None:
        """Resolve only a completed private installation, rejecting corrupt pointers."""
        value = load_json(self.pointer, None)
        if value is None:
            return None
        name = value.get("directory") if isinstance(value, dict) else None
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name in {"", ".", ".."}
        ):
            raise ValueError("环境安装记录无效")
        layout = value.get("layout", "versions")
        if not isinstance(layout, str) or layout not in {"v", "versions"}:
            raise ValueError("环境安装记录布局无效")
        versions = self.root / layout
        path = versions / name
        if (
            not path.is_dir()
            or not path.resolve().is_relative_to(versions.resolve())
            or not (path / "complete.json").is_file()
        ):
            raise ValueError("环境安装不完整，请重新准备")
        receipt = load_json(path / "complete.json", None)
        if (
            not isinstance(receipt, dict)
            or receipt.get("revision") != value.get("revision")
            or not isinstance(receipt.get("artifacts"), dict)
            or not receipt["artifacts"]
            or any(
                not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest)
                for digest in receipt["artifacts"].values()
            )
            or hashlib.sha256((path / "complete.json").read_bytes()).hexdigest()
            != value.get("receipt_sha256")
        ):
            raise ValueError("环境安装记录校验失败")
        return path

    def publish(self, path: Path) -> None:
        """Switch the pointer only after the caller verifies the prepared runtime."""
        if path.parent != self.root / "v":
            raise ValueError("环境版本不属于此插件")
        atomic_save_json(
            self.pointer,
            {
                "directory": path.name,
                "layout": "v",
                "revision": self.revision,
                "receipt_sha256": hashlib.sha256(
                    (path / "complete.json").read_bytes()
                ).hexdigest(),
            },
        )

    async def prepare(
        self,
        build: Callable[[Path], Awaitable[None]],
        progress: Callable[[str, int, int], None],
        *,
        source: Path | None = None,
        import_asset: str | None = None,
    ) -> Path:
        """Acquire fixed resources, build privately and rename a complete generation."""
        with exclusive_file_lease(self.root / "prepare.lock"):
            # Under the lease, any staging left by a killed host is garbage.
            if (self.root / "s").exists():
                shutil.rmtree(self.root / "s")
            self._require_space(source, import_asset)
            generation = uuid4().hex[:12]
            staging = self.root / "s" / generation
            staging.mkdir(parents=True)
            try:
                await acquire_resources(
                    self.artifacts,
                    self.root,
                    staging,
                    progress,
                    source=source,
                    import_asset=import_asset,
                )
                await build(staging)
                atomic_save_json(
                    staging / "complete.json",
                    {
                        "revision": self.revision,
                        "artifacts": {
                            item.name: item.sha256 for item in self.artifacts
                        },
                    },
                )
                # The receipt carries the revision; repeating it in filesystem
                # paths breaks native libraries with MAX_PATH-sensitive internals.
                destination = self.root / "v" / generation
                destination.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(destination)
                return destination
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    def _missing_bytes(self, source: Path | None, import_asset: str | None) -> int:
        """Bytes still to be written into the download cache by this preparation."""
        bundled = source is not None and source.suffix.lower() == ".zip"
        missing = 0
        for item in self.artifacts:
            if bundled or (source is not None and item.name == import_asset):
                # Imports are always copied in full, replacing any cached bytes.
                missing += item.size
                continue
            cached = self.root / "downloads" / item.name
            partial = cached.with_name(cached.name + ".part")
            existing = cached if cached.is_file() else partial
            present = existing.stat().st_size if existing.is_file() else 0
            missing += max(item.size - present, 0)
        return missing

    def _require_space(self, source: Path | None, import_asset: str | None) -> None:
        """Fail before any copy or extraction when the volume cannot hold the result."""
        required = required_space(
            self._missing_bytes(source, import_asset), self.installed_size
        )
        free = shutil.disk_usage(self.root).free
        if free < required:
            raise RuntimeError(
                f"磁盘空间不足：需要约 {required / GIB:.1f} GB，"
                f"剩余 {free / GIB:.1f} GB（{environment_path(self.root)}）"
            )

    def discard_superseded(self, *, keep_versions: bool) -> None:
        """After publication, drop the download cache, staging and other versions.

        ``keep_versions`` retains every version directory while a service that
        may run from an older one is still alive. A preparation in progress in
        another generation owns the cache; it prunes after its own publication.
        """
        try:
            with exclusive_file_lease(self.root / "prepare.lock"):
                current = self.current()
                for name in ("downloads", "s"):
                    if (self.root / name).exists():
                        shutil.rmtree(self.root / name)
                if keep_versions:
                    return
                for layout in ("v", "versions"):
                    versions = self.root / layout
                    for entry in versions.iterdir() if versions.is_dir() else ():
                        if entry != current:
                            shutil.rmtree(entry)
        except LeaseBusy:
            return

    def remove(self) -> None:
        """Delete every installed version, the pointer, caches and staging.

        The caller guarantees that no service runs from this root. Lock and log
        files stay; the pointer goes first, so an interrupted removal already
        reads as not installed.
        """
        with exclusive_file_lease(self.root / "prepare.lock"):
            self.pointer.unlink(missing_ok=True)
            for entry in self.root.iterdir():
                if entry.name in _RETAINED:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
