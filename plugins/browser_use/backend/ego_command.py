"""Execute fixed ego scripts and exchange UTF-8 results through owned files."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from shiori_sdk.processes import Processes

from .ego_runtime import EgoRuntime


class EgoActionError(RuntimeError):
    """An acknowledged helper failure with its original structured error signals."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    @property
    def recoverable(self) -> bool:
        """Keep only known completed argument/ref failures and user-control pauses."""
        if (
            self.details.get("mayHaveLateEffects") is True
            or self.details.get("executionStopped") is False
        ):
            return False
        # ego 0.6.1.13 has no common timeout code: waits can throw a plain
        # Error, while exhausted element waits are transient resolution errors.
        # Unknown failures retire the Space; diagnostic wording is never parsed.
        return (
            self.details.get("name") == "ElementResolutionError"
            and self.details.get("kind") == "permanent"
        ) or self.details.get("error_code") in {
            "EGO_INVALID_ARGUMENT",
            "EGO_TASK_SPACE_USER_IN_CONTROL",
        }


class EgoCommand:
    """Own only the CLI process; embedded work is disposed by the session owner."""

    def __init__(self, root: Path, runtime: EgoRuntime, processes: Processes) -> None:
        self.root, self.runtime, self.processes = root, runtime, processes

    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run one new script, drain diagnostics, and read its explicit result receipt."""
        identifier = uuid4().hex
        script = self.root / (identifier + ".mjs")
        output = self.root / (identifier + ".json")
        runner = Path(__file__).with_name("ego_runner.mjs").resolve().as_uri()
        envelope = {
            **request,
            "root": self.root.as_posix(),
            "output": output.as_posix(),
        }
        script.write_text(
            f"const {{ run }} = await import({json.dumps(runner)});\n"
            f"await run({json.dumps(envelope, ensure_ascii=False)});\n",
            encoding="utf-8",
        )
        process, owner = await self.processes.spawn(
            str(self.runtime.executable),
            "nodejs",
            "-e",
            f"await import('{script.as_uri()}')",
            env=dict(os.environ),
            cwd=str(self.root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # ego may start its user-owned GUI. A kill-on-close Job would also
            # kill that GUI, and killing the CLI never stops embedded scripts.
            own_process_tree=False,
        )
        acknowledged = False
        try:
            stdout, stderr = await process.communicate()
            if process.returncode != 0 or not output.is_file():
                detail = (stderr or stdout).decode("utf-8", errors="replace")[-4000:]
                raise RuntimeError(f"ego(lite) 执行失败，请检查浏览器连接：{detail}")
            result = json.loads(output.read_text(encoding="utf-8"))
            acknowledged = True
            if not result.get("ok"):
                details = result.get("details")
                raise EgoActionError(
                    str(result.get("error", "ego 操作失败")),
                    details=details if isinstance(details, dict) else None,
                )
            return result
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if owner is not None:
                owner.close()
            # Keep the session state and cancellation latch; individual scripts
            # are immutable while running and unnecessary after their CLI ends.
            if acknowledged:
                script.unlink(missing_ok=True)
                output.unlink(missing_ok=True)
