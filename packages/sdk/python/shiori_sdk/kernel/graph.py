"""Static plugin graph: replacement, conflicts, duplicate providers, cycles and order."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .contracts import KernelError, KernelState, PluginSpec
from .diagnostics import PluginDiagnostic


@dataclass(frozen=True)
class Plan:
    """Outcome of planning a set of specs before any setup runs.

    ``order`` lists plugins by dependency depth, then plugin id (§8.1),
    including register-only specs so rank stays stable. ``excluded`` maps
    plugins that must not load to the reason. ``owners`` maps each key a
    single runnable plugin declares to that plugin, or, when none does, to one
    register-only plugin that declares it.
    """

    order: tuple[str, ...]
    excluded: dict[str, PluginDiagnostic]
    owners: dict[str, str]


def _refused(
    code: str, field: str, reason: str, state: str = KernelState.BLOCKED
) -> PluginDiagnostic:
    return PluginDiagnostic(code, "dependency", field, reason, state=state)


def plan(specs: Sequence[PluginSpec], core: Collection[str]) -> Plan:
    """Plans ``specs`` against the ``core`` keys the host already provides.

    ``replaces``, ``conflicts`` and two undeclared providers of one key are
    decided only among runnable specs (D24: a disabled or register-only plugin
    is not enabled, so it cannot block one that is). A ``requires`` cycle is
    refused only when every member is runnable (§8.5); a register-only member
    is not blocked and does not relabel its runnable partner as a cycle.
    Raises ``KernelError`` when a runnable plugin declares a core key.
    """
    live = sorted(specs, key=lambda spec: spec.id)
    run = {spec.id for spec in live if spec.runnable}
    excluded: dict[str, PluginDiagnostic] = {}
    for spec in live:
        for other in set(spec.replaces) & run if spec.id in run else ():
            reason = f"插件 {other} 已被 {spec.id} 替换"
            excluded[other] = _refused(
                "replaced", "replaces", reason, KernelState.REPLACED
            )
    replaced = set(excluded)
    for spec in live:
        # A replaced plugin's own conflicts do not fire, and neither do a
        # register-only plugin's: conflicts mean "cannot be enabled together".
        if spec.id not in run or spec.id in replaced:
            continue
        for other in set(spec.conflicts) & (run - replaced - {spec.id}):
            for one, two in ((spec.id, other), (other, spec.id)):
                reason = f"插件 {one} 与 {two} 冲突，不能同时启用"
                excluded[one] = _refused("conflict", "conflicts", reason)
    providers: dict[str, list[str]] = {}
    for spec in live:
        for name in spec.provides if spec.id in run and spec.id not in excluded else ():
            if name in core:
                reason = f"插件 {spec.id} 与核心重复提供 {name}"
                code, field = "duplicate_provider", "provides"
                raise KernelError(code, "dependency", field, reason, [spec.id])
            providers.setdefault(name, []).append(spec.id)
    for name, held in providers.items():
        reason = f"插件 {'、'.join(held)} 都提供 {name}，且未声明 replaces/conflicts"
        for owner in held if len(held) > 1 else ():
            excluded[owner] = _refused("duplicate_provider", "provides", reason)
    owners = {name: held[0] for name, held in providers.items() if len(held) == 1}
    # A register-only provider still owns a key no runnable spec claimed, so a
    # dependent reads "未启用或加载失败" rather than "不存在". Core keys stay the host's.
    for spec in live:
        for name in spec.provides if not spec.runnable else ():
            if name not in core:
                _ = owners.setdefault(name, spec.id)

    def edges(spec: PluginSpec, names: Iterable[str]) -> list[str]:
        found = {owners[name] for name in names if name in owners}
        return sorted(found - {spec.id} - excluded.keys())

    # Only runnable ``requires`` form a cycle. Edges into a register-only
    # owner are ordering edges, not cycle edges: the runnable side stays
    # loadable and blocks later as an unavailable dependency. Optional
    # injection may be mutual and merely orders plugins where it can.
    runnable_deps = {
        spec.id: [dep for dep in edges(spec, spec.requires) if dep in run]
        for spec in live
        if spec.id in run and spec.id not in excluded
    }
    for members in _cycles(runnable_deps):
        reason = "插件依赖成环: " + " -> ".join((*members, members[0]))
        for member in members:
            excluded[member] = _refused("dependency_cycle", "requires", reason)
    deps = {
        spec.id: edges(spec, (*spec.requires, *spec.optional))
        for spec in live
        if spec.id not in excluded
    }
    depth: dict[str, int] = {}

    def measure(node: str, trail: tuple[str, ...] = ()) -> int:
        if node not in depth:
            below = [measure(d, (*trail, node)) for d in deps[node] if d not in trail]
            depth[node] = 1 + max(below, default=-1)
        return depth[node]

    order = tuple(sorted(deps, key=lambda node: (measure(node), node)))
    return Plan(order, excluded, owners)


def _cycles(deps: Mapping[str, Sequence[str]]) -> list[tuple[str, ...]]:
    """Every dependency cycle met by a depth-first walk, as the members in order."""
    visiting: list[str] = []
    done: set[str] = set()
    found: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        visiting.append(node)
        for dep in deps[node]:
            if dep in visiting:
                found.append(tuple(visiting[visiting.index(dep) :]))
            elif dep not in done:
                visit(dep)
        _ = visiting.pop()
        done.add(node)

    # ``visit`` marks everything it reaches done, so each node is entered once.
    _ = [visit(node) for node in deps if node not in done]
    return found


def dependents(
    target: str,
    specs: Mapping[str, PluginSpec],
    owners: Mapping[str, str],
    optional: bool,
) -> set[str]:
    """``target`` plus every plugin in ``specs`` that (transitively) injects from it.

    With ``optional`` the consumers through ``optional_inject`` count too: a
    reload resets them with their provider, so none keeps the old instance
    (§8.2); disabling only takes the ``requires`` dependents.
    """
    found = {target}
    grew = True
    while grew:
        grew = False
        for spec in specs.values():
            names = (*spec.requires, *(spec.optional if optional else ()))
            if spec.id not in found and any(owners.get(n) in found for n in names):
                found.add(spec.id)
                grew = True
    return found
