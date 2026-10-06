"""Acquire a complete fixed resource set from HTTP or a native-selected bundle."""

import os
import zipfile
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from pathlib import Path

import httpx

from .artifacts import Artifact, acquire_artifact


async def acquire_resources(
    artifacts: Sequence[Artifact],
    root: Path,
    staging: Path,
    progress: Callable[[str, int, int], None],
    *,
    source: Path | None,
    import_asset: str | None,
) -> None:
    """Keep resumable cache bytes private and link only verified artifacts into staging."""
    total, completed = sum(item.size for item in artifacts), 0
    with ExitStack() as stack:
        bundle = (
            stack.enter_context(zipfile.ZipFile(source))
            if source and source.suffix.lower() == ".zip"
            else None
        )
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=httpx.Timeout(60, connect=15)
        ) as client:
            for item in artifacts:
                progress(item.name, completed, total)
                await acquire_artifact(
                    item,
                    root / "downloads" / item.name,
                    lambda amount: progress(item.name, completed + amount, total),
                    source=(
                        source
                        if source and not bundle and item.name == import_asset
                        else None
                    ),
                    bundle=bundle,
                    client=client,
                )
                destination = staging / "downloads" / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Both paths belong to this private root and share a volume. Cleanup
                # unlinks staging; it never mutates the immutable verified cache.
                os.link(root / "downloads" / item.name, destination)
                completed += item.size
    progress("正在构建独立环境", total, total)
