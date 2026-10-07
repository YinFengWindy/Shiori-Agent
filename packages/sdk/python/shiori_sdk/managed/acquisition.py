"""Acquire a complete fixed resource set from HTTP or a native-selected original."""

import os
import zipfile
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from pathlib import Path

import httpx

from .artifacts import Artifact, acquire_artifact, verify_file


def is_bundle(source: Path | None) -> bool:
    """A ZIP import carries every artifact; any other import is one artifact."""
    return source is not None and source.suffix.lower() == ".zip"


async def acquire_resources(
    artifacts: Sequence[Artifact],
    root: Path,
    staging: Path,
    progress: Callable[[str, int, int], None],
    *,
    source: Path | None,
    import_asset: str | None,
) -> dict[str, Path]:
    """Verify every artifact and return where the build reads each one.

    Downloads are cached privately under ``root`` and hard-linked into
    ``staging/downloads``. A ZIP import is read in place and its members are
    extracted into ``staging/downloads``. A single imported artifact is only
    verified and returned at its original path: it is never copied, and the
    caller must not delete it.
    """
    total, completed = sum(item.size for item in artifacts), 0
    resources: dict[str, Path] = {}
    imported = None if source is None or is_bundle(source) else import_asset
    # A selected original is verified first, so a wrong file fails before any
    # download or extraction.
    ordered = sorted(artifacts, key=lambda item: item.name != imported)
    with ExitStack() as stack:
        bundle = (
            stack.enter_context(zipfile.ZipFile(source))
            if source is not None and is_bundle(source)
            else None
        )
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=httpx.Timeout(60, connect=15)
        ) as client:
            for item in ordered:
                progress(item.name, completed, total)

                def report(amount: int, name: str = item.name, done: int = completed):
                    progress(name, done + amount, total)

                destination = staging / "downloads" / item.name
                if source is not None and item.name == imported:
                    await verify_file(item, source, report)
                    resources[item.name] = source
                elif bundle is not None:
                    await acquire_artifact(
                        item, destination, report, bundle=bundle, client=client
                    )
                    resources[item.name] = destination
                else:
                    cached = root / "downloads" / item.name
                    await acquire_artifact(item, cached, report, client=client)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # Both paths belong to this install root and share a volume.
                    # Cleanup unlinks staging; it never mutates the verified cache.
                    os.link(cached, destination)
                    resources[item.name] = destination
                completed += item.size
    progress("正在构建独立环境", total, total)
    return resources
