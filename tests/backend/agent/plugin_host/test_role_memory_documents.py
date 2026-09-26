from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent.plugin_host.role_memory_documents import register_role_memory_documents
from core.roles import RoleStore
from desktop_bridge.method_policy import Concurrency


@pytest.mark.asyncio
async def test_registration_owns_a_read_only_role_scoped_request(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    rpc = SimpleNamespace(register=Mock())
    ctx = SimpleNamespace(
        plugin_id="default_memory", workspace=tmp_path, role_store=store, rpc=rpc
    )

    register_role_memory_documents(ctx)

    name, handler = rpc.register.call_args.args
    assert name == "roles.memory.documents"
    assert rpc.register.call_args.kwargs == {"concurrency": Concurrency.READ_ONLY}
    response = await handler({"role_id": "mira"})
    assert response["role_id"] == "mira"
    assert len(response["documents"]) == 5


def test_registration_requires_the_host_role_store(tmp_path):
    ctx = SimpleNamespace(plugin_id="akasha", workspace=tmp_path, role_store=None)

    with pytest.raises(RuntimeError, match="akasha.*role_store"):
        register_role_memory_documents(ctx)
