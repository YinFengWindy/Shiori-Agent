"""按产品扩展点划分的 capability 实现：插件只拿到 manifest 声明的窄接口。"""

from __future__ import annotations

from collections.abc import Iterable

from shiori_sdk.kernel import Scope


def contribute_to_list[T](
    target: list[T],
    item: T,
    *,
    effects: Scope,
    label: str,
) -> None:
    """把一项贡献登记进目标列表，并登记"从列表移除"的可回滚 effect。

    列表型 capability（channel / bot command）
    共用此实现，保证登记与撤销形状一致；移除守卫使重复处置保持幂等。
    """
    effects.ensure_active(label)
    target.append(item)

    def discard() -> None:
        if item in target:
            target.remove(item)

    _ = effects.effect(discard, label)


class ContributionsByPlugin[T]:
    """Each plugin's contributed objects, read back in a given plugin order.

    The storage behind a ``PluginContributionService``: a plugin's view adds to
    ``of(plugin_id)`` with ``contribute_to_list`` (so disposal withdraws it), and
    ``active`` returns what the active plugins contributed.
    """

    def __init__(self) -> None:
        self._by_plugin: dict[str, list[T]] = {}

    def of(self, plugin_id: str) -> list[T]:
        """The (live) list holding ``plugin_id``'s contributions."""
        return self._by_plugin.setdefault(plugin_id, [])

    def active(self, plugin_ids: Iterable[str]) -> list[T]:
        """The contributions of ``plugin_ids``, plugin by plugin in that order."""
        return [item for pid in plugin_ids for item in self._by_plugin.get(pid, ())]
