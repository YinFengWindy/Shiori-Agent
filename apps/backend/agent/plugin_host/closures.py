"""Enable, disable and reload closure selection, including D14 refusals."""

from collections.abc import Collection, Sequence, Mapping
from shiori_sdk.kernel import Kernel, KernelError
from agent.plugin_host.record import PluginRecord, records_by_id, find_record
from agent.plugin_host.reload import hot_unload_blockers
from agent.plugin_host.state import PluginView, PluginInstance
from agent.plugin_host.unload import (
    PluginReloadUnsupported,
    PluginRestartRequired,
    PluginReloadTimeout,
)


def restart_only(error: KernelError) -> PluginReloadUnsupported:
    """Maps the kernel's restart-only refusal to the host's reload error."""
    assert error.diagnostic.code == "restart_required", error
    reason = "channels" if error.diagnostic.field == "channels" else "hot_unload"
    return PluginReloadUnsupported(list(error.plugin_ids), reason)


def assert_hot_unloadable(
    name: str | None,
    candidates: list[PluginRecord],
    active_plugin_ids: Collection[str],
    kernel: Kernel,
) -> None:
    """Reject an unsafe closure before releasing any accepted resources."""
    by_id = records_by_id(candidates)
    records = [by_id[pid] for pid in active_plugin_ids]
    if name is not None:
        record = find_record(candidates, name)
        records = (
            [by_id[pid] for pid in kernel.closure(record.manifest.id, optional=False)]
            if record and record.manifest.id in active_plugin_ids
            else []
        )
    if unsafe := hot_unload_blockers(records):
        raise PluginRestartRequired(unsafe)


def _views_by_id(views: Sequence[PluginView]) -> dict[str, PluginView]:
    return {
        view.plugin_id: view
        for view in views
        if view.record.admission is None or view.record.admission.state != "CONFLICT"
    }


def enable_closure(
    target: PluginView,
    views: Sequence[PluginView],
    active_plugin_ids: Collection[str],
    kernel: Kernel,
) -> list[PluginView]:
    """Select the existing dependency closure for this enablement change."""
    by_id = _views_by_id(views)
    for dependency in target.record.manifest.dependencies:
        provider = by_id.get(dependency)
        if provider is not None and provider.state not in {
            "ACTIVE",
            "DISABLED",
        }:
            raise PluginReloadUnsupported([dependency], "failed")
    blocked = [
        view.plugin_id
        for view in views
        if view.state == "BLOCKED" and view.record.admission is None
    ]
    return [
        by_id[plugin_id]
        for plugin_id in (
            kernel.closure(
                target.plugin_id,
                optional=True,
                among=[*blocked, *active_plugin_ids],
            )
        )
    ]


def disable_closure(
    target: PluginView,
    views: Sequence[PluginView],
    kernel: Kernel,
) -> list[PluginView] | None:
    """Select the existing dependency closure for this enablement change."""
    by_id = _views_by_id(views)
    if target.state == "ACTIVE":
        return [
            by_id[plugin_id]
            for plugin_id in (kernel.closure(target.plugin_id, optional=True))
        ]
    if target.state == "RESTART_REQUIRED":
        raise PluginReloadUnsupported([target.plugin_id], "failed")
    if target.record.admission is None and target.state in {"FAILED", "BLOCKED"}:
        return [target]
    return None


def reload_closure(
    target: PluginView, views: Sequence[PluginView], kernel: Kernel, retired: bool
) -> list[PluginView]:
    """Reject an inactive/restart-only target before selecting reload members."""
    if retired:
        raise PluginReloadUnsupported([target.plugin_id], "retired")
    if target.state != "ACTIVE":
        raise PluginReloadUnsupported(
            [target.plugin_id],
            "disabled" if target.state == "DISABLED" else "failed",
        )
    members = kernel.closure(target.plugin_id, optional=True)
    if refusal := kernel.restart_only(members):
        raise restart_only(refusal) from refusal
    by_id = _views_by_id(views)
    return [by_id[pid] for pid in members]


def refuse_restart_only(closure: Sequence[PluginView], kernel: Kernel) -> None:
    """Reject the entire closure if any member requires a generation restart."""
    if refusal := kernel.restart_only(view.plugin_id for view in closure):
        raise restart_only(refusal)


async def drain_closure(
    closure: list[PluginRecord],
    timeout: float,
    kernel: Kernel,
    instances: Mapping[str, PluginInstance],
) -> None:
    """Seal one dependent at a time; an abandoned drain reopens every old gate."""
    gates = {
        record.manifest.id: instances[record.manifest.id].calls for record in closure
    }

    async def seal(plugin_id: str) -> None:
        gates[plugin_id].seal()
        await gates[plugin_id].wait_idle()

    try:
        await kernel.drain(list(gates), timeout, seal)
    except BaseException as error:
        for gate in gates.values():
            gate.reopen()
        if isinstance(error, KernelError):
            raise PluginReloadTimeout(error.plugin_ids, timeout) from error
        raise
