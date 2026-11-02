"""Required precompiled renderer contributions and React peer declarations."""

from dataclasses import dataclass
from pathlib import Path

from shiori_sdk.kernel import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.package_artifacts import validate_artifact
from agent.plugin_host.package_schema import object_field, string_list, compatible_range


@dataclass(frozen=True)
class RendererEntry:
    """One required precompiled ESM contribution and its own CSS files."""

    kind: str
    entry: str
    css: tuple[str, ...]
    export_name: str | None = None


def validate_renderer(
    root: Path, raw: dict[str, object], host: HostRuntimeContract
) -> tuple[RendererEntry, ...]:
    """Validate all declared renderer entries and host-provided React peers."""
    declarations = object_field(
        raw.get("renderer", {}), "renderer", {"ui", "background", "surface"}
    )
    frontend = raw.get("frontend", {})
    named_exports: tuple[str, ...] = ()
    if isinstance(frontend, dict) and "exports" in frontend:
        if declarations:
            raise PackageContractError(
                "invalid_manifest",
                "frontend",
                "Frontend cannot also declare renderer entries",
            )
        named_exports = string_list(frontend.get("exports"), "frontend.exports")
        if (
            not named_exports
            or len(set(named_exports)) != len(named_exports)
            or set(named_exports) - {"ui", "background", "surface"}
        ):
            raise PackageContractError(
                "invalid_manifest",
                "frontend.exports",
                "Expected unique named frontend contributions",
            )
        declarations = {name: frontend for name in named_exports}
    elif frontend:
        raise PackageContractError(
            "invalid_manifest",
            "frontend",
            "Installed frontend requires compiled exports and css",
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
        field = "frontend" if named_exports else f"renderer.{kind}"
        entry = object_field(
            value,
            field,
            {"entry", "css", "exports"} if named_exports else {"entry", "css"},
        )
        module = validate_artifact(
            root,
            entry.get("entry"),
            f"{field}.entry",
            ".mjs",
            export_name=kind if named_exports else "default",
        )
        css = string_list(entry.get("css"), f"{field}.css")
        for index, path in enumerate(css):
            _ = validate_artifact(root, path, f"{field}.css[{index}]", ".css")
        entries.append(
            RendererEntry(kind, module, css, kind if named_exports else None)
        )
    return tuple(entries)
