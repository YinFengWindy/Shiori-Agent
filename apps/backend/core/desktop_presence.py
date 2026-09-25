"""Latest desktop presence reported by the Electron host."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DesktopPresence:
    """Holds whether the user is at the desktop, for choosing where to reach them.

    The desktop host reports only changes (screen lock, 10 minutes of system
    idle, resumed activity). Until the first report arrives the user counts as
    present, so a runtime without a desktop host keeps treating the desktop as
    the place the user is.
    """

    def __init__(self) -> None:
        self._present = True

    def is_desktop_present(self) -> bool:
        """Returns the latest reported presence, or True before any report."""
        return self._present

    def report(self, present: bool) -> None:
        """Stores one report from the desktop host."""
        if present != self._present:
            logger.info("[desktop-presence] present=%s", present)
        self._present = present
