"""Validate one compiled frontend namespace before any plugin code executes."""

from dataclasses import dataclass
from pathlib import Path

from shiori_sdk import __version__
from shiori_sdk.kernel import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.package_artifacts import validate_artifact
from agent.plugin_host.package_schema import object_field, string_list, compatible_range


@dataclass(frozen=True)
class FrontendEntry:
    """One ESM artifact, its declared contributions, CSS and shared peer constraints."""

    entry: str
    exports: tuple[str, ...]
    css: tuple[str, ...]


def validate_frontend(
    root: Path, raw: dict[str, object], host: HostRuntimeContract
) -> FrontendEntry | None:
    """Reject missing exports, unsafe artifacts and incompatible host peers."""
    if "frontend" not in raw:
        return None
    declaration = object_field(
        raw["frontend"], "frontend", {"entry", "css", "exports", "peers"}
    )
    names = string_list(declaration.get("exports"), "frontend.exports")
    if (
        not names
        or len(set(names)) != len(names)
        or set(names) - {"ui", "background", "surface"}
    ):
        raise PackageContractError(
            "invalid_manifest",
            "frontend.exports",
            "Expected unique named frontend contributions",
        )
    peers = object_field(
        declaration.get("peers", {}),
        "frontend.peers",
        {"react", "react-dom", "@yinfengwindy/shiori-sdk"},
    )
    versions = {**host.renderer_peers, "@yinfengwindy/shiori-sdk": __version__}
    if set(peers) != set(versions):
        raise PackageContractError(
            "missing_dependency",
            "frontend.peers",
            "Frontend requires React, React DOM and Shiori SDK peers",
        )
    for name, expression in peers.items():
        _ = compatible_range(versions[name], expression, f"frontend.peers.{name}")
    for name in names:
        module = validate_artifact(
            root, declaration.get("entry"), "frontend.entry", ".mjs", export_name=name
        )
    css = string_list(declaration.get("css"), "frontend.css")
    for index, path in enumerate(css):
        _ = validate_artifact(root, path, f"frontend.css[{index}]", ".css")
    return FrontendEntry(module, names, css)
