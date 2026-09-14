"""插件句柄与生命周期状态机：内核对每个插件包的全部运行时记账。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable

from agent.plugin_host.capabilities import PluginContributions
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.diagnostics import PackageContractError


class PluginState(Enum):
    """显式生命周期状态；失败与禁用是终态，ACTIVE 可转 UNLOADING。"""

    DISCOVERED = auto()
    DISABLED = auto()
    LOADING = auto()
    ACTIVE = auto()
    UNLOADING = auto()
    DISPOSED = auto()
    FAILED = auto()
    BLOCKED = auto()
    UNTRUSTED = auto()
    CONFLICT = auto()
    RESTART_REQUIRED = auto()


@dataclass
class PluginRecord:
    """discover() 产出的静态描述：目录、入口与 manifest。"""

    name: str
    plugin_dir: Path
    entry_file: Path
    import_path: str
    manifest: PluginManifest


@dataclass
class PluginHandle:
    """单个插件的运行时记账：状态、效果作用域、贡献与实例。"""

    record: PluginRecord
    state: PluginState = PluginState.DISCOVERED
    effects: EffectScope = field(default_factory=lambda: EffectScope("unbound"))
    contributions: PluginContributions = field(default_factory=PluginContributions)
    instance: Any = None
    drainers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)
    error: BaseException | None = None

    @property
    def plugin_id(self) -> str:
        return self.record.manifest.id

    def describe(self) -> dict[str, Any]:
        """Returns a diagnostic snapshot used by logs and inspection."""
        return {
            "id": self.plugin_id,
            "state": self.state.name,
            "dir": str(self.record.plugin_dir),
            "error": str(self.error) if self.error else "",
            "diagnostic": (
                self.error.diagnostic.to_dict()
                if self.state is PluginState.BLOCKED
                and isinstance(self.error, PackageContractError)
                else None
            ),
        }
