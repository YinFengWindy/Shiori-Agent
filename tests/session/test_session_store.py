from __future__ import annotations

from pathlib import Path

from session.store import SessionStore


def test_fetch_session_messages_resolves_legacy_media_path(tmp_path: Path) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    current_image = workspace / "private_runtime" / "novelai" / "output.png"
    current_image.parent.mkdir(parents=True)
    current_image.write_bytes(b"png")
    legacy_image = (
        tmp_path
        / ".akashic"
        / "workspace"
        / "private_runtime"
        / "novelai"
        / "output.png"
    )
    store = SessionStore(workspace / "sessions.db")
    store.create_session(key="role:mira", metadata={})
    store.insert_message(
        "role:mira",
        role="assistant",
        content="image",
        ts="2026-07-13T12:00:00+08:00",
        seq=0,
        media=[str(legacy_image)],
    )

    messages = store.fetch_session_messages("role:mira")

    assert messages[0]["media"] == [str(current_image)]
    store.close()
