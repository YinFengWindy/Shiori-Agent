"""OS-backed ownership and durable uncertainty shared across plugin generations."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from uuid import uuid4

from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.files.lease import LeaseBusy, exclusive_file_lease


class InstanceBusy(RuntimeError):
    """Another live provider owner still holds the real inference operation."""


class InferenceUncertain(RuntimeError):
    """An interrupted transport cannot prove that upstream inference has ended."""

    def __init__(self):
        super().__init__("推理完成状态未知；请重建外部 GPT-SoVITS 服务后重新连接")


class InstanceState:
    """A private file lock survives Python module/generation boundaries."""

    def __init__(self, root: Path):
        self.root = root
        self.marker = root / "inference.json"

    @contextmanager
    def lease(self):
        """Acquire nonblocking ownership; a live owner cannot be reset by reconnect."""
        try:
            with exclusive_file_lease(self.root / "instance.lock"):
                yield
        except LeaseBusy as error:
            raise InstanceBusy(
                "上一请求仍在等待服务响应，实例由其他活动任务占用"
            ) from error

    def status(self) -> dict[str, object]:
        """Distinguish a known live operation from a marker left after a lost owner."""
        try:
            with self.lease():
                busy = False
        except InstanceBusy:
            busy = True
        record = load_json(self.marker, None)
        return {
            "busy": busy,
            "recovery_required": record is not None and not busy,
            "instance": record,
        }

    @asynccontextmanager
    async def wait(self):
        """Queue asynchronously behind a live owner, including another generation."""
        async with AsyncExitStack() as stack:
            while True:
                try:
                    stack.enter_context(self.lease())
                    break
                except InstanceBusy:
                    await asyncio.sleep(0.05)
            yield

    def begin(self, url: str, managed: dict[str, str] | None = None) -> str:
        """Publish one unique operation while holding the instance lease."""
        operation = uuid4().hex
        atomic_save_json(
            self.marker,
            {
                "operation": operation,
                "url": url,
                "state": "in_flight",
                **({"managed": managed} if managed else {}),
            },
        )
        return operation

    def finish(self, operation: str, *, unknown: bool = False) -> None:
        """A late owner must never clear or overwrite another operation's marker."""
        record = load_json(self.marker, None)
        if not isinstance(record, dict) or record.get("operation") != operation:
            return
        if unknown:
            atomic_save_json(self.marker, {**record, "state": "unknown"})
        else:
            self.marker.unlink(missing_ok=True)

    def recover(self) -> None:
        """Clear uncertainty only under an exclusive lease after explicit restart."""
        self.marker.unlink(missing_ok=True)

    def recover_owned(
        self, *, url: str | None = None, runtime: str | None = None
    ) -> None:
        """Called under both ownership proofs; external records are never auto-cleared."""
        record = load_json(self.marker, None)
        if not isinstance(record, dict):
            return
        managed = record.get("managed")
        if not isinstance(managed, dict) or not isinstance(
            managed.get("generation"), str
        ):
            return
        if (url is not None and record.get("url") == url) or managed.get(
            "runtime"
        ) == runtime:
            self.recover()
