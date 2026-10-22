"""Static plugin graph: replacement, conflicts, duplicate providers, cycles and order."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .contracts import KernelError, KernelState, PluginSpec
from .diagnostics import PluginDiagnostic


@dataclass(frozen=True)
class Plan:
    """Outcome of planning a set of specs before any setup runs.

    ``order`` lists the loadable plugins by dependency depth, then plugin id
    (§8.1). ``excluded`` maps plugins that must not load to the reason.
    ``owners`` maps each key a single plugin declares to that plugin.
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

    ``replaces`` keeps the replaced plugin from loading at all; ``conflicts``
    and two undeclared providers of one key block both sides, naming each
    other (D24); every plugin on a ``requires`` cycle is blocked (§8.5). Raises
    ``KernelError`` when a plugin declares a key the core provides.
    """
    live = sorted(specs, key=lambda spec: spec.id)
    ids = {spec.id for spec in live}
    excluded: dict[str, PluginDiagnostic] = {}
    for spec in live:
        for other in set(spec.replaces) & ids:
            reason = f"插件 {other} 已被 {spec.id} 替换"
            excluded[other] = _refused(
                "replaced", "replaces", reason, KernelState.REPLACED
            )
    replaced = set(excluded)
    for spec in live:
        for other in set(spec.conflicts) & (ids - replaced - {spec.id}):
            if spec.id in replaced:
                break
            for one, two in ((spec.id, other), (other, spec.id)):
                reason = f"插件 {one} 与 {two} 冲突，不能同时启用"
                excluded[one] = _refused("conflict", "conflicts", reason)
    providers: dict[str, list[str]] = {}
    for spec in live:
        for name in spec.provides if spec.id not in excluded else ():
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

    def edges(spec: PluginSpec, names: Iterable[str]) -> list[str]:
        found = {owners[name] for name in names if name in owners}
        return sorted(found - {spec.id} - excluded.keys())

    # Only ``requires`` can form a cycle; optional injection may be mutual and
    # merely orders the plugins where it can.
    for cycle in _cycles(
        {s.id: edges(s, s.requires) for s in live if s.id not in excluded}
    ):
        reason = "插件依赖成环: " + " -> ".join((*cycle, cycle[0]))
        for member in cycle:
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

    for node in deps:
        if node not in done:
            visit(node)
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
            if spec.id not in found and any(
                owners.get(name) in found
                for name in (*spec.requires, *(spec.optional if optional else ()))
            ):
                found.add(spec.id)
                grew = True
    return found
