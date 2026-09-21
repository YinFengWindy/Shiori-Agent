"""Real OS lease blocks separate generations even on the same event-loop thread."""

import subprocess
import sys

import pytest

from plugins.computer_use.backend.lease import DesktopLease


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named semaphore")
def test_lease_excludes_generations_and_processes_then_releases():
    lease = DesktopLease()
    try:
        with pytest.raises(RuntimeError, match="占用"):
            DesktopLease()
        code = "from plugins.computer_use.backend.lease import DesktopLease; DesktopLease()"
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, timeout=10
        )
        assert result.returncode != 0
        assert b"RuntimeError" in result.stderr
    finally:
        lease.close()
    successor = DesktopLease()
    successor.close()
