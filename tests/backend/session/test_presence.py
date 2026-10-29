"""Presence heartbeats use the existing session columns."""

from __future__ import annotations

from datetime import datetime, timezone

from session.manager import SessionManager


def test_presence_records_user_and_initiated_on_the_role_session(tmp_path):
    manager = SessionManager(tmp_path)
    when = datetime(2026, 10, 28, 1, 2, 3, tzinfo=timezone.utc)
    later = datetime(2026, 10, 28, 4, 5, 6, tzinfo=timezone.utc)
    manager.get_or_create("role:mira")
    desktop = manager.get_or_create("desktop:1")
    desktop.metadata["role_id"] = "mira"
    manager.save(desktop)

    manager.presence.record_user_message("desktop:1", when)
    manager.presence.record_initiated_sent("role:mira", later)

    assert manager.presence.last_user_at("role:mira") == when
    assert manager.presence.last_user_at("desktop:1") == when
    assert manager.presence.last_initiated_at("role:mira") == later
    assert manager.presence.last_user_at("desktop:other") is None
