"""Enable, disable and reload closure selection, including D14 refusals."""

from collections.abc import Callable, Collection, Sequence, Mapping
from dataclasses import replace
from shiori_sdk.kernel import Kernel, KernelError, PluginSpec
from shiori_sdk.kernel.graph import dependents, plan
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
    return {view.plugin_id: view for view in views if not view.record.is_conflicting}


def enable_closure(
    target: PluginView,
    views: Sequence[PluginView],
    active_plugin_ids: Collection[str],
    kernel: Kernel,
) -> list[PluginView]:
    """Select blocked dependents and active optional consumers when enabling a target."""
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
    """Select running dependents for disablement, or an inactive target alone."""
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


def relation_closure(
    target: PluginView,
    enabled: bool,
    closure: list[PluginView] | None,
    views: Sequence[PluginView],
    kernel: Kernel,
    make_spec: Callable[[PluginRecord], PluginSpec],
) -> list[PluginView] | None:
    """Include relation exclusions and their consumers before any live setup changes.

    The same SDK planner decides relation precedence and future key ownership.
    This preview grants no resources; real admission and core-key collision
    checks still run before setup. Both old and future consumers must settle.
    """
    if closure is None:
        return None
    by_id = _views_by_id(views)
    specs = [make_spec(view.record) for view in by_id.values()]
    updated = [
        (
            replace(spec, runnable=enabled and target.record.admission is None)
            if spec.id == target.plugin_id
            else spec
        )
        for spec in specs
    ]
    before = plan(specs, ()).excluded
    following = plan(updated, ())
    after = following.excluded
    changed = {
        plugin_id
        for plugin_id in before.keys() | after.keys()
        if before.get(plugin_id) != after.get(plugin_id)
        and any(
            diagnostic is not None
            and diagnostic.code in {"replaced", "conflict", "duplicate_provider"}
            for diagnostic in (before.get(plugin_id), after.get(plugin_id))
        )
    }
    # Trust admission can make a default-enabled spec runnable before this
    # toggle. Its currently live opponents still need to leave the old graph.
    changed.update(
        plugin_id
        for plugin_id, diagnostic in after.items()
        if diagnostic.code in {"replaced", "conflict", "duplicate_provider"}
        and by_id[plugin_id].state == "ACTIVE"
    )
    members = {view.plugin_id for view in closure}
    pool = [
        view.plugin_id
        for view in views
        if view.record.admission is None and view.state in {"ACTIVE", "BLOCKED"}
    ]
    for plugin_id in changed:
        members.update(kernel.closure(plugin_id, optional=True, among=pool))
        members.update(
            dependents(
                plugin_id,
                {spec.id: spec for spec in updated if spec.id in {*pool, plugin_id}},
                following.owners,
                optional=True,
            )
        )
    rank = {plugin_id: index for index, plugin_id in enumerate(kernel.order())}
    return [
        by_id[plugin_id]
        for plugin_id in sorted(
            members, key=lambda pid: (rank.get(pid, -1), pid), reverse=True
        )
    ]


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
