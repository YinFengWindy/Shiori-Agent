from __future__ import annotations

import pytest

from core.desktop_presence import DesktopPresence
from desktop_bridge.runtime.desktop_presence import report_desktop_presence


def test_report_stores_presence_and_echoes_it():
    presence = DesktopPresence()
    assert report_desktop_presence(presence, {"present": False}) == {"present": False}
    assert presence.is_desktop_present() is False


@pytest.mark.parametrize("payload", [{}, {"present": "false"}, {"present": 0}])
def test_non_boolean_report_is_rejected_without_changing_state(payload):
    presence = DesktopPresence()
    presence.report(False)
    with pytest.raises(ValueError, match="present"):
        report_desktop_presence(presence, payload)
    assert presence.is_desktop_present() is False
