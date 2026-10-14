"""Explicit destinations and recorded reports without a host conversation store."""

from dataclasses import dataclass, field


@dataclass
class FakeBackgroundResultTarget:
    """Record one result per ID, matching the SDK's in-process deduplication."""

    role_id: str = "test-role"
    thread_id: str = "test-thread"
    reports: dict[str, str] = field(default_factory=dict)

    async def report(self, result_id: str, text: str) -> bool:
        """Return False for a repeated result identifier."""
        if not result_id.strip() or not text.strip():
            raise ValueError("后台结果标识和正文不能为空")
        if result_id in self.reports:
            return False
        self.reports[result_id] = text
        return True


class FakeBackgroundResults:
    """Capture an explicitly configured fake destination."""

    def __init__(self) -> None:
        self.target: FakeBackgroundResultTarget | None = None

    def capture(self) -> FakeBackgroundResultTarget:
        """Require a test to declare the origin instead of inventing one."""
        if self.target is None:
            raise PermissionError("测试未提供后台结果目标")
        return self.target
