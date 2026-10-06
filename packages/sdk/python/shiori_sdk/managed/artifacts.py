"""Bounded, cancellable acquisition of immutable provider-selected artifacts."""

import asyncio
import hashlib
import zipfile
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class Artifact:
    """An exact upstream object; names are relative within an installation."""

    name: str
    url: str
    size: int
    sha256: str

    def __post_init__(self):
        path = Path(self.name)
        if path.is_absolute() or ".." in path.parts or ":" in self.name:
            raise ValueError("无效的资源路径")
        if self.size < 1 or len(self.sha256) != 64:
            raise ValueError("资源必须固定大小和 SHA-256")


async def acquire_artifact(
    artifact: Artifact,
    destination: Path,
    progress: Callable[[int], None],
    *,
    source: Path | None = None,
    bundle: zipfile.ZipFile | None = None,
    client: httpx.AsyncClient,
) -> None:
    """Resume verified ranges, retaining interrupted bytes but never publishing them."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    digest, received = hashlib.sha256(), 0
    existing = destination if destination.exists() else partial
    if existing.exists() and source is None and bundle is None:
        with existing.open("rb") as previous:
            while chunk := previous.read(1024 * 1024):
                received += len(chunk)
                digest.update(chunk)
                progress(received)
                await asyncio.sleep(0)
        if received == artifact.size and digest.hexdigest() == artifact.sha256:
            if existing == partial:
                partial.replace(destination)
            return
        if existing == destination or received >= artifact.size:
            existing.unlink()
            digest, received = hashlib.sha256(), 0
    try:
        with partial.open("ab" if received else "wb") as output:

            def write(chunk: bytes):
                nonlocal received
                received += len(chunk)
                if received > artifact.size:
                    raise ValueError(f"资源超过固定大小：{artifact.name}")
                output.write(chunk)
                digest.update(chunk)
                progress(received)

            if source is not None or bundle is not None:
                if bundle is not None:
                    info = bundle.getinfo(artifact.name)
                    if info.file_size != artifact.size or info.is_dir():
                        raise ValueError(f"导入资源大小不匹配：{artifact.name}")
                    stream = bundle.open(info)
                else:
                    if source is None or source.stat().st_size != artifact.size:
                        raise ValueError(f"导入资源大小不匹配：{artifact.name}")
                    stream = source.open("rb")
                with stream:
                    while chunk := stream.read(1024 * 1024):
                        write(chunk)
                        await asyncio.sleep(0)
            else:
                async with client.stream(
                    "GET",
                    artifact.url,
                    headers={"Range": f"bytes={received}-"} if received else {},
                ) as response:
                    response.raise_for_status()
                    if received and response.status_code == 200:
                        # A server may ignore Range; never append a whole file to its prefix.
                        output.seek(0)
                        output.truncate()
                        digest, received = hashlib.sha256(), 0
                    elif response.status_code == 206:
                        match = re.fullmatch(
                            r"bytes (\d+)-(\d+)/(\d+)",
                            response.headers.get("content-range", ""),
                        )
                        if (
                            not match
                            or int(match[1]) != received
                            or int(match[3]) != artifact.size
                            or int(match[2]) != artifact.size - 1
                        ):
                            raise ValueError(f"资源断点范围无效：{artifact.name}")
                    elif response.status_code != 200:
                        raise ValueError(f"资源下载响应无效：{artifact.name}")
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        write(chunk)
        if received != artifact.size or digest.hexdigest() != artifact.sha256:
            raise ValueError(f"资源 SHA-256 或大小不匹配：{artifact.name}")
        partial.replace(destination)
    except ValueError:
        # Interrupted transfers are reusable; invalid content/ranges are not.
        partial.unlink(missing_ok=True)
        raise
