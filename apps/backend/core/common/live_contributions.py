"""按来源实时派生的对象：来源内容变化时才重建。

插件贡献（阶段模块、proactive gate 等）每次使用时从插件内核读取当前 ACTIVE
插件的贡献；由贡献派生出的对象（``Phase``、gate 链）构造时有排序与校验开销，
所以只在贡献集合变化时重建。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

ItemT = TypeVar("ItemT")
BuiltT = TypeVar("BuiltT")


class LiveContributions(Generic[ItemT, BuiltT]):
    """每次 ``current()`` 重新读取 ``source``，元素按身份与顺序都未变时复用上次结果。

    构造时立即按当前来源构建一次，构建错误（如名字或 slot 冲突）在接线处暴露；
    之后只有来源内容变化才会重新构建与校验。
    """

    def __init__(
        self,
        source: Callable[[], Sequence[ItemT]],
        build: Callable[[list[ItemT]], BuiltT],
    ) -> None:
        self._source = source
        self._build = build
        self._items = tuple(source())
        self._built = build(list(self._items))

    def current(self) -> BuiltT:
        """返回与来源当前内容一致的构建结果，必要时重建。"""
        items = tuple(self._source())
        if not _same_items(items, self._items):
            # 先构建再记录：构建失败时下一次仍会重试。
            self._built = self._build(list(items))
            self._items = items
        return self._built


def _same_items(left: tuple[object, ...], right: tuple[object, ...]) -> bool:
    # 按身份比较：元素可能按字段定义了 __eq__，重载后的新实例必须重建。
    return len(left) == len(right) and all(a is b for a, b in zip(left, right))
