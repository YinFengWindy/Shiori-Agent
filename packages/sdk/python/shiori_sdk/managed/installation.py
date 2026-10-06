"""Immutable version directories and an atomically published current pointer."""

import shutil
import hashlib
import re
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import uuid4

from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.files.lease import exclusive_file_lease

from .artifacts import Artifact
from .acquisition import acquire_resources


class Installation:
    """A failed or cancelled preparation never changes the previous usable version."""

    def __init__(self, root: Path, revision: str, artifacts: Sequence[Artifact]):
        self.root, self.revision, self.artifacts = root, revision, tuple(artifacts)
        self.pointer = root / "current.json"

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
        path = self.root / "versions" / name
        if (
            not path.is_dir()
            or not path.resolve().is_relative_to((self.root / "versions").resolve())
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
        if path.parent != self.root / "versions":
            raise ValueError("环境版本不属于此插件")
        atomic_save_json(
            self.pointer,
            {
                "directory": path.name,
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
            staging = self.root / "staging" / uuid4().hex
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
                destination = (
                    self.root / "versions" / (self.revision + "-" + uuid4().hex)
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(destination)
                return destination
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
