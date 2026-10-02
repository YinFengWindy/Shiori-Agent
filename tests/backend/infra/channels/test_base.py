from pathlib import Path

import pytest

from infra.channels.base import AttachmentStore, SessionIdentityIndex
from session.manager import SessionManager


def test_attachment_store_writes_under_configured_root(tmp_path: Path):
    store = AttachmentStore(tmp_path / "uploads")

    path = store.write_bytes(b"hello", prefix="img_", suffix=".png")

    assert path.parent == tmp_path / "uploads"
    assert path.suffix == ".png"
    assert path.read_bytes() == b"hello"


def test_attachment_store_uses_default_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    monkeypatch.setattr(
        "infra.channels.base.resolve_default_workspace",
        lambda: workspace,
    )

    assert AttachmentStore().root == workspace / "uploads"


@pytest.mark.asyncio
async def test_session_identity_index_rebuilds_and_persists_metadata(tmp_path: Path):
    manager = SessionManager(tmp_path)
    existing = manager.get_or_create("telegram:123")
    existing.metadata["username"] = "alice"
    manager.save(existing)

    index = SessionIdentityIndex(
        manager,
        channel="telegram",
        metadata_key="username",
        normalizer=lambda value: value.lower(),
    )

    rebuilt = index.rebuild()
    assert rebuilt == {"alice": "123"}
    assert index.resolve("ALICE") == "123"

    await index.remember("Bob", "456")

    assert index.mapping["bob"] == "456"
    saved = manager.get_or_create("telegram:456")
    assert saved.metadata["username"] == "bob"
