"""Persist browser acceptance steps and per-generation native diagnostics."""

from collections.abc import Awaitable, Callable
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import time
import traceback
from typing import Any, TypeVar

from shiori_sdk.tools import ToolResult

_Result = TypeVar("_Result")


def _exception_details(error: BaseException) -> dict[str, str]:
    return {
        "type": type(error).__name__,
        "message": str(error),
        "traceback": "".join(traceback.format_exception(error)),
    }


class BrowserAcceptanceEvidence:
    """Save failed/cancelled attempts immediately and keep each daemon log distinct."""

    def __init__(self, directory: Path, metadata: dict[str, Any]) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.report: dict[str, Any] = {
            "versions": metadata,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "steps": [],
            "generations": [],
        }
        self._logs: dict[str, tuple[Path, Path]] = {}
        self._current_generation: str | None = None
        self.save()

    async def run(
        self,
        name: str,
        operation: Callable[[], Awaitable[_Result]],
        arguments: dict[str, Any] | None = None,
    ) -> _Result:
        """Record the attempted operation without changing its failure semantics."""
        step: dict[str, Any] = {
            "operation": name,
            "arguments": arguments or {},
            "status": "running",
            "generation": self._current_generation,
        }
        self.report["steps"].append(step)
        started = time.perf_counter()
        self.save()
        try:
            result = await operation()
            if isinstance(result, (str, ToolResult)):
                step["text"] = result.text if isinstance(result, ToolResult) else result
                step["image_blocks"] = (
                    len(result.content_blocks) if isinstance(result, ToolResult) else 0
                )
            step["status"] = "passed"
            return result
        except BaseException as error:
            step["status"] = (
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
            )
            step["error"] = _exception_details(error)
            raise
        finally:
            # Starting the first tool also creates its generation inside operation.
            if step["generation"] is None or name == "open":
                step["generation"] = self._current_generation
            step["elapsed_seconds"] = round(time.perf_counter() - started, 6)
            self.save()

    def daemon_started(self, session: str, pid: int, log: Path) -> None:
        """Associate native process identity with the current action generation."""
        if session in self._logs:
            raise ValueError(f"Duplicate native generation: {session}")
        destination = self.directory / f"daemon-{len(self._logs) + 1:02d}.log"
        self._logs[session] = log, destination
        self._current_generation = session
        self.report["generations"].append(
            {"session": session, "pid": pid, "log": destination.name}
        )
        self.save()

    def daemon_stopped(self, session: str) -> None:
        """Copy a closed generation's log before profile reuse overwrites it."""
        source, destination = self._logs[session]
        destination.write_bytes(source.read_bytes())
        self.save()

    def finish(self, error: BaseException | None = None) -> None:
        """Capture assertion failures as well as errors recorded by individual steps."""
        self.report["status"] = "passed" if error is None else "failed"
        if error is not None:
            self.report["error"] = _exception_details(error)
        self.report["finished_at"] = datetime.now(UTC).isoformat()
        self.save()

    def save(self) -> None:
        """Atomically persist progress so cleanup cannot discard earlier failures."""
        path = self.directory / "acceptance.json"
        pending = path.with_suffix(".json.tmp")
        pending.write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        pending.replace(path)
