from __future__ import annotations

from core.common.live_contributions import LiveContributions


class _Module:
    def __init__(self, slot: str) -> None:
        self.slot = slot


def test_live_contributions_rebuild_only_when_source_changes() -> None:
    """来源移除/新增后按当前内容重建，内容不变时复用上次结果（#855）。"""
    first = _Module("plugin_a.mark")
    active: list[_Module] = [first]
    builds: list[list[_Module]] = []

    def build(items: list[_Module]) -> list[str]:
        builds.append(items)
        return [item.slot for item in items]

    live = LiveContributions(lambda: active, build)

    assert live.current() == ["plugin_a.mark"]
    assert live.current() is live.current()
    active.clear()
    assert live.current() == []
    active.append(_Module("plugin_b.mark"))
    assert live.current() == ["plugin_b.mark"]
    # 同 slot 的新实例（插件重载后）也必须重建，不能复用旧对象。
    active[0] = _Module("plugin_b.mark")
    _ = live.current()
    assert len(builds) == 4
