"""Host-owned native services; plugins supply commands and own their policy."""

from pathlib import Path
import sys
from typing import BinaryIO
from agent.mcp.client import McpClient
from bootstrap.paths import common_emojis_paths, resource_root
from infra.process.owned_spawn import spawn_owned, popen_owned
from shiori_sdk.processes import Processes, Resources


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
    ):
        """Assign child ownership before allowing executable code to run."""
        return await spawn_owned(
            *command, env=env, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr
        )

    def as_capability(self) -> Processes:
        """Check MCP and process results at their real construction point."""
        return self

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


class HostResources:
    """Resolve host-distributed resources in source and frozen installations."""

    @property
    def root(self) -> Path:
        """Return the configured host resource root."""
        return resource_root()

    def common_emojis(self, workspace: Path) -> tuple[Path, ...]:
        """Return user overrides followed by the packaged emoji resource."""
        return tuple(common_emojis_paths(workspace))

    def as_capability(self) -> Resources:
        """Validate source/frozen path access without exporting bootstrap modules."""
        return self
