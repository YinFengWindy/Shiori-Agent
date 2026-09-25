from __future__ import annotations

from core.desktop_presence import DesktopPresence


def test_present_before_any_report():
    assert DesktopPresence().is_desktop_present() is True


def test_latest_report_wins():
    presence = DesktopPresence()
    presence.report(False)
    assert presence.is_desktop_present() is False
    presence.report(True)
    assert presence.is_desktop_present() is True
