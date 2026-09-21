"""Direct ownership of the fixed agent-browser daemon and its persistent diagnostics."""

import asyncio
from pathlib import Path
from typing import BinaryIO

from agent.mcp.windows_job import WindowsJob


class BrowserDaemon:
    """Starts the official daemon entry under a Job before MCP can issue commands."""

    def __init__(self, executable: Path, profile: Path, env: dict[str, str]) -> None:
        self._executable, self._profile, self._env = executable, profile, env
        self._process: asyncio.subprocess.Process | None = None
        self._job: WindowsJob | None = None
        self._log: BinaryIO | None = None

    async def start(self, timeout: float) -> None:
        """Waits for a listening owned socket; a live PID alone is not readiness."""
        socket_dir = (
            Path(self._env["AGENT_BROWSER_SOCKET_DIR"])
            / "namespaces"
            / self._env["AGENT_BROWSER_NAMESPACE"]
            / "run"
        )
        socket_dir.mkdir(parents=True, exist_ok=True)
        session = self._env["AGENT_BROWSER_SESSION"]
        # v0.38.1 connection.rs::daemon_config_fingerprint, verified against
        # this fixed binary: debug=false, policies=None, idle_timeout=Some("0"),
        # default_timeout=None, no_auto_dialog=false. Other launch flags are not
        # part of this daemon-owned fingerprint. Never adopt an existing session.
        with (socket_dir / (session + ".config")).open("x", encoding="utf-8") as config:
            config.write("785b971085b3e7e9")
        self._log = (self._profile / "daemon.log").open("w+b")
        try:
            async with asyncio.timeout(timeout):
                self._process = await asyncio.create_subprocess_exec(
                    str(self._executable),
                    env={**self._env, "AGENT_BROWSER_DAEMON": "1"},
                    cwd=str(self._profile),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=self._log,
                    stderr=self._log,
                    creationflags=0x08000004,
                )
                self._job = WindowsJob(self._process.pid, resume=True)
                port_file = socket_dir / (session + ".port")
                while True:
                    if self._process.returncode is not None:
                        self._log.seek(0)
                        raise RuntimeError(
                            "Browser Use daemon 启动失败："
                            + self._log.read().decode("utf-8", errors="replace")
                        )
                    if port_file.is_file():
                        port = int(port_file.read_text(encoding="utf-8").strip())
                        try:
                            _, writer = await asyncio.open_connection("127.0.0.1", port)
                        except ConnectionRefusedError:
                            pass  # The daemon publishes its port just before listening.
                        else:
                            writer.close()
                            await writer.wait_closed()
                            return
                    await asyncio.sleep(0.02)
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Kills all owned native children before closing the daemon log."""
        try:
            if self._job is not None:
                self._job.close()
                self._job = None
        finally:
            try:
                if self._process is not None:
                    if self._process.returncode is None:
                        self._process.kill()
                    await asyncio.wait_for(self._process.wait(), 5)
                    self._process = None
            finally:
                if self._log is not None:
                    self._log.close()
                    self._log = None
