"""External manifest contract, dependency gates and every required contribution."""

import pytest
import yaml

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.package_contract import validate_package


def _change(package, **values):
    path = package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(values)
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")


def test_valid_package_separates_identity_version_and_runtime(contract_package):
    result = validate_package(contract_package)
    assert result.manifest.version == "1.2.3"
    assert result.runtime_api == ">=2.0.0 <3.0.0"
    assert [entry.kind for entry in result.renderer] == ["ui", "background", "surface"]


@pytest.mark.parametrize(
    "values, code, field",
    [
        ({"runtime_api": ">=3.0.0 <4.0.0"}, "incompatible_runtime", "runtime_api"),
        ({"version": "1.2"}, "invalid_version", "version"),
        ({"package_contract": True}, "unsupported_contract", "package_contract"),
        ({"package_contract": 2}, "unsupported_contract", "package_contract"),
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
        (
            {"host_dependencies": {"python": ["not-installed"]}},
            "missing_dependency",
            "host_dependencies.python[0]",
        ),
        (
            {"host_dependencies": {"npm": ["lodash"]}},
            "invalid_manifest",
            "host_dependencies",
        ),
        ({"assets": ["../secret"]}, "invalid_path", "assets[0]"),
        ({"entry": "backend/missing.py"}, "missing_file", "entry"),
        (
            {"peer_dependencies": {"react": "20.0.0", "react-dom": "19.2.0"}},
            "incompatible_runtime",
            "peer_dependencies.react",
        ),
        ({"unknown": True}, "invalid_manifest", "manifest"),
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


def test_declared_host_python_dependency_uses_host_inventory(contract_package):
    _change(contract_package, host_dependencies={"python": ["pydantic"]})
    host = HostRuntimeContract(python_dependencies=frozenset({"pydantic"}))
    assert validate_package(contract_package, host=host).manifest.id == "external_demo"


def test_external_boundary_does_not_accept_legacy_manifest(contract_package):
    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    del raw["package_contract"]
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.field == "package_contract"


@pytest.mark.parametrize(
    "values, field", [({"api": 2.0}, "api"), ({"id": "con"}, "id")]
)
def test_external_schema_rejects_noninteger_api_and_device_id(
    contract_package, values, field
):
    _change(contract_package, **values)
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.field == field


def test_external_package_may_declare_channels(contract_package):
    _change(
        contract_package,
        capabilities=["channels"],
        runtime_api=">=2.2.0 <3.0.0",
        channels=[{"name": "demo_chat", "label": "Demo"}],
    )
    result = validate_package(contract_package)
    assert [item.name for item in result.manifest.channels] == ["demo_chat"]


def test_external_channel_declaration_errors_block_the_package(contract_package):
    _change(
        contract_package,
        capabilities=["channels"],
        channels=[{"name": "desktop", "label": "Desktop"}],
    )
    with pytest.raises(PackageContractError) as caught:
        validate_package(contract_package)
    assert caught.value.diagnostic.code == "invalid_manifest"
    assert "desktop" in caught.value.diagnostic.reason


def test_host_advertises_runtime_api_with_channel_hooks():
    assert HostRuntimeContract().runtime_api == "2.5.0"
