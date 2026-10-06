"""Exclusive owned-loopback service startup with generation identity verification."""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

import httpx
from shiori_sdk.files.lease import LeaseBusy, exclusive_file_lease
from shiori_sdk.processes import Processes

from .child import OwnedChild

type Launch = Callable[[Path, int, str], tuple[list[str], Path, dict[str, str]]]


class OwnedService:
    """Readiness must come from this child token, never an arbitrary occupied port."""

    def __init__(self, root: Path, processes: Processes, launch: Launch):
        self.root, self.launch = root, launch
        self.child = OwnedChild(processes)
        self.lease = ExitStack()
        self.url: str | None = None
        self.token: str | None = None
        self.ready = False
        self.on_stopped: Callable[[str], Awaitable[None]] | None = None
        self.before_start: Callable[[], Awaitable[None]] | None = None

    async def start(self, installation: Path, *, timeout: float = 180) -> None:
        """Start one service; cancellation or startup failure releases its entire tree."""
        if self.child.process is not None:
            raise RuntimeError("托管服务已经运行")
        self.ready = False
        try:
            # New generations are constructed before the predecessor is drained.
            # Waiting in this background task keeps setup free to finish that transition.
            async with asyncio.timeout(timeout):
                while True:
                    try:
                        self.lease.enter_context(
                            exclusive_file_lease(self.root / "service.lock")
                        )
                        break
                    except LeaseBusy:
                        await asyncio.sleep(0.1)
                if self.before_start is not None:
                    # Every owner holds this lease until its native tree has exited.
                    # Host crashes close its Windows Job before a replacement can own it.
                    await self.before_start()
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            token = uuid4().hex
            self.token = token
            command, cwd, env = self.launch(installation, port, token)
            self.url = f"http://127.0.0.1:{port}"
            await self.child.start(
                command, cwd=cwd, env=env, log=self.root / "service.log"
            )
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                    while True:
                        process = self.child.process
                        if process is None or process.returncode is not None:
                            raise RuntimeError(
                                f"托管服务提前退出，详见 {self.root / 'service.log'}"
                            )
                        try:
                            response = await client.get(self.url + "/shiori-runtime")
                        except (httpx.ConnectError, httpx.TimeoutException):
                            # Model loading is expected to bind its socket only after initialization.
                            await asyncio.sleep(0.25)
                            continue
                        response.raise_for_status()
                        if response.json() != {"token": token}:
                            raise RuntimeError("端口被其他服务占用，未连接该服务")
                        if process.returncode is not None:
                            raise RuntimeError("托管服务已退出")
                        self.ready = True
                        return
        except BaseException:
            await self.close()
            raise

    def require_url(self) -> str:
        """Fail explicitly when the selected managed process is unavailable."""
        if (
            not self.ready
            or not self.url
            or self.child.process is None
            or self.child.process.returncode is not None
        ):
            raise RuntimeError("托管环境未运行，请先准备或启动环境")
        return self.url

    async def close(self) -> None:
        """Clear uncertainty only through a callback after an actually owned child exits."""
        self.ready = False
        previous = self.url if self.child.process is not None else None
        try:
            await self.child.close()
            if previous is not None and self.on_stopped is not None:
                await self.on_stopped(previous)
        finally:
            if self.child.process is None:
                self.url = None
                self.token = None
                self.lease.close()
