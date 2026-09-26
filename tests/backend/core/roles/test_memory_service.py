from core.roles.memory_service import RoleMemoryService
from core.roles.store import RoleStore


def test_read_documents_is_role_scoped_and_never_initializes_missing_files(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.create_role(name="Luna", system_prompt="luna", role_id="luna")
    mira_root = tmp_path / "roles" / "mira" / "memory"
    luna_root = tmp_path / "roles" / "luna" / "memory"
    mira_root.mkdir(parents=True)
    luna_root.mkdir(parents=True)
    (mira_root / "SELF.md").write_text("# Mira", encoding="utf-8")
    (mira_root / "MEMORY.md").write_text("  \n", encoding="utf-8")
    (luna_root / "SELF.md").write_text("# Luna", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in mira_root.iterdir()}

    documents = RoleMemoryService(tmp_path).read_documents("mira")

    assert len(documents) == 5
    assert documents[0] == {"name": "MEMORY.md", "status": "empty", "content": "  \n"}
    assert documents[1] == {"name": "SELF.md", "status": "ready", "content": "# Mira"}
    assert all(item["status"] == "missing" for item in documents[2:])
    assert {path.name: path.read_bytes() for path in mira_root.iterdir()} == before
    assert (luna_root / "SELF.md").read_text(encoding="utf-8") == "# Luna"


def test_one_document_read_error_does_not_hide_other_documents(tmp_path, monkeypatch):
    root = tmp_path / "roles" / "mira" / "memory"
    root.mkdir(parents=True)
    (root / "SELF.md").write_text("# Mira", encoding="utf-8")
    original_read = type(root).read_text

    def read_text(path, *args, **kwargs):
        if path.name == "MEMORY.md":
            raise PermissionError("denied")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(type(root), "read_text", read_text)
    documents = RoleMemoryService(tmp_path).read_documents("mira")

    assert documents[0]["status"] == "error"
    assert "denied" in documents[0]["error"]
    assert documents[1]["content"] == "# Mira"


def test_deferred_initialization_preserves_existing_self_document(tmp_path):
    role = RoleStore(tmp_path).create_role(name="Mira", system_prompt="mira")
    memory = RoleMemoryService(tmp_path)
    root = memory.ensure_initialized(role)
    self_path = root / "SELF.md"
    self_path.write_text("# 我是谁\n\n自定义角色记忆", encoding="utf-8")
    role.memory_init_state = {
        "seed_self_ready": True,
        "seed_first_impression_ready": True,
    }

    state = memory.prepare_memory(role)

    assert state["self_seed"]["status"] == "generated"
    assert self_path.read_text(encoding="utf-8") == "# 我是谁\n\n自定义角色记忆"
