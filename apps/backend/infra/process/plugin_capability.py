"""The ``processes`` plugin capability: host-owned native processes (#901 P2).

``HostProcesses`` is the ``host.processes`` core service, one per kernel
generation and shared by every plugin: plugins supply the commands and own
their policy, the host owns spawning (owned spawn, Windows Job) and MCP clients.
"""

import sys
from pathlib import Path
from typing import BinaryIO


from infra.process.mcp_client import McpClient
from infra.process.owned_spawn import popen_owned, spawn_owned


class HostProcesses:
    """Use existing MCP, owned spawn and Windows Job implementations."""

    def mcp(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        own_process_tree: bool = False,
        inherit_env: bool = True,
    ):
        """Build one explicitly owned connection without starting it."""
        return McpClient(
            name,
            command,
            env,
            cwd,
            own_process_tree=own_process_tree,
            inherit_env=inherit_env,
        )

    async def spawn(
        self,
        *command: str,
        env: dict[str, str],
        cwd: str,
        stdin: int,
        stdout: int | BinaryIO,
        stderr: int | BinaryIO,
        own_process_tree: bool = True,
    ):
        """Assign child ownership before allowing executable code to run."""
        return await spawn_owned(
            *command,
            owned=own_process_tree,
            env=env,
            cwd=cwd,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )

    def popen(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: BinaryIO,
        stderr: int | BinaryIO,
    ):
        """Use the same suspended-spawn/WindowsJob ownership for synchronous channel children."""
        return popen_owned(
            command,
            owned=sys.platform == "win32",
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
