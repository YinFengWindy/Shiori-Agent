"""External manifest contract, dependency gates and every required contribution."""

import pytest
import yaml

from shiori_sdk import RUNTIME_API_VERSION
from shiori_sdk.kernel import PackageContractError
from agent.plugin_host.discovery import discover_plugins
from agent.plugin_host.package_contract import validate_package


def _change(package, **values):
    path = package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(values)
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")


def test_valid_package_reads_version_and_every_renderer_entry(contract_package):
    result = validate_package(contract_package)
    assert result.manifest.version == "1.2.3"
    assert [entry.kind for entry in result.renderer] == ["ui", "background", "surface"]


@pytest.mark.parametrize("distribution", ["builtin", "external"])
def test_package_accepts_host_supported_display_and_distribution_metadata(
    contract_package, distribution
):
    _change(
        contract_package,
        distribution=distribution,
        display_name="External Demo",
        category="system",
        default_enabled=False,
    )
    manifest = validate_package(contract_package).manifest
    assert manifest.distribution == distribution
    assert manifest.display_name == "External Demo"
    assert manifest.category == "system"
    assert manifest.default_enabled is False


@pytest.mark.parametrize(
    "values, code, field",
    [
        ({"runtime_api": ">=3.1.1 <4.0.0"}, "invalid_manifest", "manifest"),
        ({"version": "1.2"}, "invalid_version", "version"),
        (
            {
                "renderer": {
                    "ui": {"entry": "renderer/ui.mjs", "css": [], "optional": True}
                }
            },
            "invalid_manifest",
            "renderer.ui",
        ),
        ({"peer_dependencies": {}}, "missing_dependency", "peer_dependencies"),
        ({"assets": ["../secret"]}, "invalid_path", "assets[0]"),
        ({"entry": "backend/missing.py"}, "missing_file", "entry"),
        (
            {"peer_dependencies": {"react": "20.0.0", "react-dom": "19.2.0"}},
            "incompatible_runtime",
            "peer_dependencies.react",
        ),
        ({"unknown": True}, "invalid_manifest", "manifest"),
        ({"distribution": "unknown"}, "invalid_manifest", "manifest"),
        ({"category": "unknown"}, "invalid_manifest", "manifest"),
        ({"default_enabled": "false"}, "invalid_manifest", "manifest"),
    ],
)
def test_rejects_manifest_with_structured_diagnostics(
    contract_package, values, code, field
):
    _change(contract_package, **values)
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    diagnostic = caught.value.diagnostic.to_dict()
    assert diagnostic["code"] == code
    assert diagnostic["field"] == field
    assert diagnostic["stage"] == "validation"
    assert diagnostic["state"] == "BLOCKED"
    assert diagnostic["reason"]


@pytest.mark.parametrize("kind", ["ui", "background", "surface"])
def test_every_declared_renderer_entry_is_required(contract_package, kind):
    (contract_package / f"renderer/{kind}.mjs").unlink()
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.field == f"renderer.{kind}.entry"


def test_css_is_required(contract_package):
    (contract_package / "renderer/style.css").unlink()
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.field == "renderer.ui.css[0]"


_NO_API = object()


@pytest.mark.parametrize("api", [2, "4", 4.0, 5, _NO_API])
def test_install_and_discovery_reject_every_api_but_integer_4(contract_package, api):
    """Install refuses before the trust prompt; an installed copy is BLOCKED.

    Both report ``unsupported_api``, and the installed copy keeps its name.
    """
    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(api=api, runtime_api=">=3.1.1 <4.0.0", package_contract=1)
    if api is _NO_API:
        del raw["api"]
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert (caught.value.diagnostic.code, caught.value.diagnostic.field) == (
        "unsupported_api",
        "api",
    )
    # The directory name differs from the id, so the row must read the manifest.
    installed = contract_package.rename(contract_package.parent / "installed_copy")
    [record] = discover_plugins(
        [installed.parent],
        external_roots=[installed.parent],
        namespace="t",
        strict=True,
        host=None,
    )
    assert (record.manifest.id, record.manifest.version) == ("external_demo", "1.2.3")
    assert record.admission is not None
    assert record.admission.to_dict() == caught.value.diagnostic.to_dict() | {
        "path": str(installed / "manifest.yaml")
    }


def test_external_schema_rejects_a_device_id(contract_package):
    _change(contract_package, id="con")
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.field == "id"


def test_external_package_may_declare_channels(contract_package):
    _change(
        contract_package,
        inject=["channels"],
        contributes={
            "channels": [
                {
                    "name": "demo_chat",
                    "label": "Demo",
                    "chat_types": [
                        {"type": "private", "label": "私聊", "chat_id_label": "用户 ID"}
                    ],
                }
            ]
        },
    )
    result = validate_package(contract_package)
    assert [item.name for item in result.manifest.channels] == ["demo_chat"]


def test_external_channel_declaration_errors_block_the_package(contract_package):
    _change(
        contract_package,
        inject=["channels"],
        contributes={"channels": [{"name": "desktop", "label": "Desktop"}]},
    )
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.code == "invalid_manifest"
    assert "desktop" in caught.value.diagnostic.reason


def test_repository_plugin_declarations_admit_the_installed_sdk_and_siblings():
    import tomllib
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from bootstrap.paths import plugin_roots
    from agent.plugin_host.manifest import load_manifest

    runtime = RUNTIME_API_VERSION
    projects: dict[str, str] = {}
    dependencies: dict[str, list[Requirement]] = {}
    for root in plugin_roots():
        for directory in root.iterdir():
            if not (directory / "manifest.yaml").is_file():
                continue
            manifest = load_manifest(directory)
            assert manifest is not None
            project = tomllib.loads(
                (directory / "pyproject.toml").read_text(encoding="utf-8")
            )["project"]
            assert manifest.version == project["version"], directory.name
            name = canonicalize_name(project["name"])
            projects[name] = project["version"]
            requirements = [
                *project["dependencies"],
                *project.get("optional-dependencies", {}).get("test", []),
            ]
            sdk = [
                Requirement(value)
                for value in requirements
                if value.startswith("shiori-sdk")
            ]
            assert sdk and all(
                runtime in requirement.specifier for requirement in sdk
            ), directory.name
            dependencies[name] = [Requirement(value) for value in requirements]

    # Real package pins must resolve to the sibling wheels built for this release.
    for name, requirements in dependencies.items():
        for requirement in requirements:
            sibling = canonicalize_name(requirement.name)
            if sibling.startswith("shiori-plugin-"):
                assert sibling in projects, (name, requirement)
                assert projects[sibling] in requirement.specifier, (name, requirement)
