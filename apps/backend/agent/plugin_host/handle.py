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
from agent.plugin_host.diagnostics import (
    ChannelDeclarationError,
    PackageContractError,
    PluginDiagnostic,
    RendererActivationError,
)
from agent.plugin_host.dependencies import PluginDependencyError


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
    # An accepted load/rollback left effects that could not be fully disposed
    # (``EffectScope.dispose_all()`` reported errors) — see
    # ``PluginKernel._rollback_failed_load`` (#262). Retrying without a
    # process restart cannot guarantee a clean slate, so this is a distinct,
    # non-``can_toggle`` terminal state rather than a plain ``FAILED`` that
    # invites an immediate, unsafe retry.
    RESTART_REQUIRED = auto()


@dataclass
class PluginRecord:
    """discover() 产出的静态描述：目录、入口与 manifest。"""

    name: str
    plugin_dir: Path
    entry_file: Path
    import_path: str
    manifest: PluginManifest
    source: str = "builtin"
    admission: PluginDiagnostic | None = None
    # Captured before execution and retained across settings generations.
    fingerprint: str | None = None
    trust_directory: str = ""
    content_hashes: dict[str, str] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        """Identify one directory candidate without collapsing duplicate manifest IDs."""
        return str(self.plugin_dir.absolute())


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
    # Required renderer contribution points not yet confirmed ready by their
    # owning renderer process (#262); populated once, when the handle becomes
    # ACTIVE. Which kinds gate this — and why ``surface`` does not — is
    # documented once at ``kernel.py``'s ``_RENDERER_GATED_KINDS``. Backend
    # contributions (tools/RPC/events) are already live the moment ``setup()``
    # returns, independent of this bookkeeping; it only gates what the
    # Plugins page displays as fully "ACTIVE" (AC1), never resource grants.
    pending_renderer_kinds: frozenset[str] = frozenset()
    # Minted fresh every time this handle becomes ACTIVE (#262); a renderer
    # echoes it back in ``plugins.activation.report`` so a stale report from
    # a superseded load attempt of the same plugin id cannot be mistaken for
    # one belonging to the current handle — see
    # ``PluginKernel._find_active_handle``.
    activation_token: str = ""

    @property
    def plugin_id(self) -> str:
        return self.record.manifest.id

    def _diagnostic(self) -> dict[str, str] | None:
        """Resolves the diagnostic dict this handle should surface, if any.

        Deliberately narrow per error type rather than one broad
        ``isinstance`` check:

        - Admission rejections (``self.record.admission``) always win.
        - ``PackageContractError``/``PluginDependencyError`` only surface
          while ``state is BLOCKED`` — unchanged from before #262. A plugin
          whose own ``setup()`` *raises* one of these at runtime (rather than
          admission rejecting it beforehand) lands in ``FAILED``, and its
          diagnostic's baked-in ``state: "BLOCKED"`` would misleadingly
          contradict the handle's real state — see
          ``test_runtime_contract_error_still_rolls_back_failed_setup`` and
          the handbook's "Runtime failures retain their original error; they
          do not reuse a static BLOCKED diagnostic."
        - ``RendererActivationError`` (#262) is the new case: it is only ever
          constructed by ``PluginKernel.fail_renderer_entry`` with a
          diagnostic whose ``state`` already matches the handle's real
          FAILED/RESTART_REQUIRED state, so surfacing it is always accurate.
          ``ChannelDeclarationError`` follows the same rule: its diagnostic is
          built with ``state: "FAILED"`` for a setup rollback.
        """
        if self.record.admission is not None:
            return self.record.admission.to_dict()
        if self.state is PluginState.BLOCKED and isinstance(
            self.error, (PackageContractError, PluginDependencyError)
        ):
            return self.error.diagnostic.to_dict() if self.error.diagnostic else None
        if self.state in {
            PluginState.FAILED,
            PluginState.RESTART_REQUIRED,
        } and isinstance(
            self.error, (RendererActivationError, ChannelDeclarationError)
        ):
            return self.error.diagnostic.to_dict()
        return None

    def describe(self) -> dict[str, Any]:
        """Returns a diagnostic snapshot used by logs and inspection."""
        return {
            "id": self.plugin_id,
            "candidate_id": self.record.candidate_id,
            "source": self.record.source,
            "state": self.state.name,
            "dir": str(self.record.plugin_dir),
            "error": str(self.error) if self.error else "",
            "pending_renderer_kinds": sorted(self.pending_renderer_kinds),
            "activation_token": self.activation_token,
            "diagnostic": self._diagnostic(),
        }
