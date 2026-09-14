"""Required precompiled renderer contributions and React peer declarations."""

from dataclasses import dataclass
from pathlib import Path

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.package_artifacts import validate_artifact
from agent.plugin_host.package_schema import object_field, string_list, compatible_range


@dataclass(frozen=True)
class RendererEntry:
    """One required precompiled ESM contribution and its own CSS files."""

    kind: str
    entry: str
    css: tuple[str, ...]


def validate_renderer(
    root: Path, raw: dict[str, object], host: HostRuntimeContract
) -> tuple[RendererEntry, ...]:
    """Validate all declared renderer entries and host-provided React peers."""
    declarations = object_field(
        raw.get("renderer", {}), "renderer", {"ui", "background", "surface"}
    )
    peers = object_field(
        raw.get("peer_dependencies", {}), "peer_dependencies", {"react", "react-dom"}
    )
    if declarations and set(peers) != {"react", "react-dom"}:
        raise PackageContractError(
            "missing_dependency",
            "peer_dependencies",
            "Renderer requires react and react-dom host peers",
        )
    for name, expression in peers.items():
        version = host.renderer_peers.get(name)
        if version is None:
            raise PackageContractError(
                "missing_dependency",
                f"peer_dependencies.{name}",
                "Host does not provide peer",
            )
        _ = compatible_range(version, expression, f"peer_dependencies.{name}")
    entries: list[RendererEntry] = []
    for kind, value in declarations.items():
        field = f"renderer.{kind}"
        entry = object_field(value, field, {"entry", "css"})
        module = validate_artifact(root, entry.get("entry"), f"{field}.entry", ".mjs")
        css = string_list(entry.get("css"), f"{field}.css")
        for index, path in enumerate(css):
            _ = validate_artifact(root, path, f"{field}.css[{index}]", ".css")
        entries.append(RendererEntry(kind, module, css))
    return tuple(entries)
