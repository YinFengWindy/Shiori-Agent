"""Finite RPC extraction rejects unprovable names and derives constants from registrations."""

from pathlib import Path

import pytest

from scripts.gen_plugin_rpc import ContractError, generate, plugin_contract


def package(tmp_path: Path, source: str) -> Path:
    directory = tmp_path / "plugins" / "example"
    (directory / "backend").mkdir(parents=True)
    (directory / "manifest.yaml").write_text(
        'api: 4\nsdk: ">=4.0.0"\nid: example\n', encoding="utf-8"
    )
    (directory / "backend" / "plugin.py").write_text(source, encoding="utf-8")
    return directory


def test_registration_tables_aliases_and_imported_constants_are_the_source(
    tmp_path: Path,
):
    directory = package(
        tmp_path,
        """
from shiori_sdk.core.services import RPC as KEY
from .names import PREFIX
async def setup(ctx):
    transport = ctx.require(KEY)
    for name, handler in [("read", read), ("write", write)]:
        transport.register(PREFIX + name, handler)
""",
    )
    (directory / "backend" / "names.py").write_text(
        'PREFIX = "state."\n', encoding="utf-8"
    )
    assert plugin_contract(directory)["methods"] == ["state.read", "state.write"]
    generate(directory)
    assert '"state.read": "state.read"' in (
        directory / "rpcMethods.generated.ts"
    ).read_text(encoding="utf-8")
    (directory / "backend" / "names.py").write_text(
        'PREFIX = "changed."\n', encoding="utf-8"
    )
    with pytest.raises(ContractError, match="stale"):
        generate(directory, check=True)


def test_dynamic_registration_is_rejected_at_its_source(tmp_path: Path):
    directory = package(
        tmp_path,
        """
from shiori_sdk.core.services import RPC
async def setup(ctx):
    ctx.require(RPC).register(ctx.config['method'], handler)
""",
    )
    with pytest.raises(ContractError, match=r"plugin.py:4: RPC name"):
        plugin_contract(directory)


def test_rpc_parameter_and_class_binding_keep_service_methods_separate(tmp_path: Path):
    directory = package(
        tmp_path,
        """
from shiori_sdk.rpc import RpcCapability
from shiori_sdk.core.services import SERVICES
class API:
    def __init__(self, rpc: RpcCapability):
        self.transport = rpc
    def register(self):
        self.transport.register("read", self.read)
async def setup(ctx):
    ctx.require(SERVICES).register("voice", contract="voice.v1", methods={"speak": speak})
""",
    )
    contract = plugin_contract(directory)
    assert contract["methods"] == ["read"]
    assert contract["services"] == [
        {"service_id": "voice", "contract": "voice.v1", "methods": ["speak"]}
    ]
