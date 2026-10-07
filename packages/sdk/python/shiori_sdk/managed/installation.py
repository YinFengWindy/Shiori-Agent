"""Immutable version directories and an atomically published current pointer.

An installation has two roots. The *state root* (plugin data) keeps small
state: the ``current.json`` pointer, the ``location.json`` install-location
record, locks and logs, so a service's identity never depends on where the
environment is installed. The *install root* holds everything large: the
download cache, staging, version directories and child temp/cache files. It is
the state root unless the user chose another location.
"""

import hashlib
import logging
import os
import re
import shutil
import stat
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.files.lease import LeaseBusy, exclusive_file_lease

from .acquisition import acquire_resources, is_bundle
from .artifacts import Artifact
from .paths import environment_path, native_path

_logger = logging.getLogger(__name__)
GIB = 1024**3
# Reserve 5% of the estimate, at least 1 GiB, for logs, child temp/cache files
# and filesystem overhead that a fixed artifact list cannot enumerate.
SPACE_MARGIN_RATIO = 0.05
SPACE_MARGIN_MIN = GIB
# Entries an installation owns inside its install root: the download cache,
# staging, version directories (and the trial ``versions`` layout) and the
# child ``tmp`` / ``cache`` directories of ``private_environment``. Removal
# deletes only these and the provider-declared ``scratch`` names, never other
# files of a directory the user chose.
_INSTALLED = ("downloads", "s", "v", "versions", "tmp", "cache")

# A build reads the prepared staging directory and the verified path of every
# artifact; an imported original is read where the user keeps it.
type Build = Callable[[Path, Mapping[str, Path]], Awaitable[None]]


def required_space(missing: int, installed_size: int) -> int:
    """Bytes a preparation may add at its peak: missing artifacts, result and margin."""
    estimate = missing + installed_size
    return estimate + max(SPACE_MARGIN_MIN, int(estimate * SPACE_MARGIN_RATIO))


def free_space(path: Path) -> int | None:
    """Free bytes on the volume of ``path`` or its nearest existing ancestor.

    ``None`` when no ancestor exists, e.g. a removed drive.
    """
    for candidate in (path, *path.parents):
        if candidate.exists():
            return shutil.disk_usage(candidate).free
    return None


def _delete(path: Path) -> None:
    """Delete an owned entry; a link or junction is unlinked, never entered.

    ``shutil.rmtree`` refuses a top-level junction, and following one would
    delete files outside the installation.
    """
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    directory = stat.S_ISDIR(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x10  # FILE_ATTRIBUTE_DIRECTORY
    )
    if path.is_symlink() or path.is_junction():
        # Windows removes directory links with rmdir, file links with unlink.
        (os.rmdir if directory else os.unlink)(path)
    elif directory:
        shutil.rmtree(path)
    else:
        path.unlink()


class Installation:
    """A failed or cancelled preparation never changes the previous usable version.

    ``root`` is the state root. ``installed_size`` is the provider-declared size
    in bytes of one prepared version (extracted archives, built environment);
    together with the missing artifact bytes it bounds the free-space check
    made before any copy. ``scratch`` names further install-root directories the
    provider's children create (their own temp/cache locations), which removal
    deletes as well.
    """

    def __init__(
        self,
        root: Path,
        revision: str,
        artifacts: Sequence[Artifact],
        *,
        installed_size: int = 0,
        scratch: Sequence[str] = (),
    ):
        if installed_size < 0:
            raise ValueError("安装大小不能为负数")
        if any(Path(name).name != name or name in {"", ".", ".."} for name in scratch):
            raise ValueError("无效的环境缓存目录名")
        self.root, self.revision, self.artifacts = (
            native_path(root),
            revision,
            tuple(artifacts),
        )
        self.installed_size = installed_size
        self.entries = (*_INSTALLED, *scratch)
        self.pointer = self.root / "current.json"
        self.location = self.root / "location.json"

    @property
    def install_root(self) -> Path:
        """Where installation artifacts live; read from state on every access.

        An unreadable location record raises ``ValueError``; ``relocate`` and
        ``remove`` recover from it without reading it.
        """
        value = load_json(self.location, None)
        if value is None:
            return self.root
        recorded = value.get("root") if isinstance(value, dict) else None
        if not isinstance(recorded, str) or not Path(recorded).is_absolute():
            raise ValueError("环境安装位置记录无效，请重新选择位置或删除环境")
        return native_path(Path(recorded))

    def customized(self) -> bool:
        """Whether a chosen location replaces the default state root."""
        return self.location.exists()

    def occupied(self) -> bool:
        """Whether anything is installed or kept, i.e. a removal has work to do.

        Exactly this blocks relocation, so whatever blocks it is removable.
        """
        root = self.install_root
        return self.pointer.exists() or any(
            os.path.lexists(root / name) for name in self.entries
        )

    def relocate(self, root: Path | None) -> None:
        """Choose a new install root, or the default with ``None``.

        Only when nothing is installed or kept. A target must not already hold
        installation entries, so a preparation never prunes another
        installation's versions. An unreadable location record is replaced
        when no pointer exists: nothing recorded there can be found anyway.
        """
        target = None
        if root is not None:
            if not root.is_absolute():
                raise ValueError("安装位置必须为绝对路径")
            target = native_path(root)
            if target.exists() and not target.is_dir():
                raise ValueError("安装位置不是目录")
        with exclusive_file_lease(self.root / "prepare.lock"):
            try:
                previous: Path | None = self.install_root
                occupied = self.occupied()
            except ValueError:
                previous, occupied = None, self.pointer.exists()
            if occupied:
                raise RuntimeError("请先删除环境再更改安装位置")
            if target is None:
                self.location.unlink(missing_ok=True)
            elif target != previous and any(
                os.path.lexists(target / name) for name in self.entries
            ):
                raise ValueError("所选位置已有环境文件，请选择其他目录")
            else:
                atomic_save_json(self.location, {"root": environment_path(target)})
            # A dedicated directory this installation created and left empty.
            if (
                previous not in (None, self.root, target)
                and previous.is_dir()
                and not any(previous.iterdir())
            ):
                previous.rmdir()

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
        # A default installation records no root and follows the state root
        # wherever plugin data moves; a chosen location is recorded absolutely.
        recorded = value.get("root")
        if recorded is None:
            root = self.root
        elif isinstance(recorded, str) and Path(recorded).is_absolute():
            root = native_path(Path(recorded))
        else:
            raise ValueError("环境安装记录无效")
        if root != self.install_root:
            raise ValueError("环境安装位置与记录不一致，请删除环境后重新准备")
        versions = root / layout
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
        root = self.install_root
        if path.parent != root / "v":
            raise ValueError("环境版本不属于此插件")
        record: dict[str, str] = {
            "directory": path.name,
            "layout": "v",
            "revision": self.revision,
            "receipt_sha256": hashlib.sha256(
                (path / "complete.json").read_bytes()
            ).hexdigest(),
        }
        if self.customized():
            record["root"] = environment_path(root)
        atomic_save_json(self.pointer, record)

    async def prepare(
        self,
        build: Build,
        progress: Callable[[str, int, int], None],
        *,
        source: Path | None = None,
        import_asset: str | None = None,
    ) -> Path:
        """Acquire fixed resources, build privately and rename a complete generation.

        ``source`` is a user-selected original: a ZIP bundle of all artifacts,
        or the single artifact ``import_asset``. It is read in place and never
        copied, moved or deleted.
        """
        bundle = is_bundle(source)
        if (
            source is not None
            and not bundle
            and import_asset not in {item.name for item in self.artifacts}
        ):
            raise ValueError("环境包格式不受支持")
        with exclusive_file_lease(self.root / "prepare.lock"):
            # The location cannot change while this lease is held.
            root = self.install_root
            # Under the lease, any staging left by a killed host is garbage.
            _delete(root / "s")
            self._require_space(
                root,
                bundle=bundle,
                imported=None if source is None or bundle else import_asset,
            )
            generation = uuid4().hex[:12]
            staging = root / "s" / generation
            staging.mkdir(parents=True)
            try:
                resources = await acquire_resources(
                    self.artifacts,
                    root,
                    staging,
                    progress,
                    source=source,
                    import_asset=import_asset,
                )
                await build(staging, resources)
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
                destination = root / "v" / generation
                destination.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(destination)
                return destination
            finally:
                _delete(staging)
                # An empty staging parent would otherwise block relocation.
                if (root / "s").is_dir() and not any((root / "s").iterdir()):
                    (root / "s").rmdir()

    def _missing_bytes(self, root: Path, *, bundle: bool, imported: str | None) -> int:
        """Bytes this preparation still writes before building.

        A ZIP bundle extracts every member into staging; a single imported
        original is read in place and adds nothing.
        """
        if bundle:
            return sum(item.size for item in self.artifacts)
        missing = 0
        for item in self.artifacts:
            if item.name == imported:
                continue
            cached = root / "downloads" / item.name
            partial = cached.with_name(cached.name + ".part")
            existing = cached if cached.is_file() else partial
            present = existing.stat().st_size if existing.is_file() else 0
            missing += max(item.size - present, 0)
        return missing

    def required(self, *, imported: str | None = None, bundle: bool = False) -> int:
        """Space the free-space check demands now on the install root's volume.

        Without arguments for a download; ``imported`` for that artifact read in
        place, ``bundle`` for a ZIP import of every artifact.
        """
        missing = self._missing_bytes(
            self.install_root, bundle=bundle, imported=imported
        )
        return required_space(missing, self.installed_size)

    def _require_space(self, root: Path, *, bundle: bool, imported: str | None) -> None:
        """Fail before any copy or extraction when the volume cannot hold the result."""
        required = required_space(
            self._missing_bytes(root, bundle=bundle, imported=imported),
            self.installed_size,
        )
        root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(root).free
        if free < required:
            raise RuntimeError(
                f"磁盘空间不足：需要约 {required / GIB:.1f} GiB，"
                f"剩余 {free / GIB:.1f} GiB（{environment_path(root)}）"
            )

    def discard_superseded(self, *, keep_versions: bool) -> None:
        """After publication, drop the download cache, staging and other versions.

        ``keep_versions`` retains every version directory while a service that
        may run from an older one is still alive. A preparation in progress in
        another generation owns the cache; it prunes after its own publication.
        """
        try:
            with exclusive_file_lease(self.root / "prepare.lock"):
                root = self.install_root
                current = self.current()
                for name in ("downloads", "s"):
                    _delete(root / name)
                if keep_versions:
                    return
                for layout in ("v", "versions"):
                    versions = root / layout
                    if versions.is_dir() and not versions.is_junction():
                        for entry in versions.iterdir():
                            if entry != current:
                                _delete(entry)
        except LeaseBusy:
            _logger.info("另一实例正在准备环境，跳过清理：%s", self.root)

    def reclaimable(self) -> tuple[int, bool]:
        """Kept download bytes and whether unfinished staging is left over.

        Cheap enough for a polled status: one stat per known artifact (and its
        ``.part``), and staging is only probed for any entry, never walked.
        Entries deleted concurrently are simply absent.
        """
        root = self.install_root
        total = 0
        for item in self.artifacts:
            cached = root / "downloads" / item.name
            for path in (cached, cached.with_name(cached.name + ".part")):
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        try:
            with os.scandir(root / "s") as entries:
                staged = any(True for _entry in entries)
        except OSError:
            staged = False
        return total, staged

    def remove(self) -> None:
        """Delete the pointer, then every installation entry of the install root.

        The caller guarantees that no service runs from this root. State files
        (location, locks, logs, provider configuration) stay in the state root;
        the pointer goes first, so an interrupted removal already reads as not
        installed. A chosen install root left empty is deleted too. An
        unreadable location record is reset to the default: the installation it
        named cannot be found, so only the pointer and default entries go.
        """
        with exclusive_file_lease(self.root / "prepare.lock"):
            self.pointer.unlink(missing_ok=True)
            try:
                root = self.install_root
            except ValueError:
                self.location.unlink()
                root = self.root
            for name in self.entries:
                _delete(root / name)
            if root != self.root and root.is_dir() and not any(root.iterdir()):
                root.rmdir()
