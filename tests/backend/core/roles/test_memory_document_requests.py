import pytest

from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService
from core.roles.store import RoleStore


@pytest.mark.asyncio
async def test_reader_restricts_documents_to_a_persisted_role(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    store.create_role(role_id="luna", name="Luna", system_prompt="test")
    for role_id in ("mira", "luna"):
        root = tmp_path / "roles" / role_id / "memory"
        root.mkdir(parents=True)
        (root / "SELF.md").write_text(role_id, encoding="utf-8")
    reader = RoleMemoryDocumentReader(store, RoleMemoryService(tmp_path))

    result = await reader.read({"role_id": "mira"})

    assert result["role_id"] == "mira"
    assert (
        next(item for item in result["documents"] if item["name"] == "SELF.md")[
            "content"
        ]
        == "mira"
    )
    assert "luna" not in str(result)
    with pytest.raises(ValueError, match="role not found"):
        await reader.read({"role_id": "missing"})
