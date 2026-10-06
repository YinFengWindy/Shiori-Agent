"""A failed native termination cannot be mistaken for released process ownership."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.managed.child import OwnedChild
from shiori_sdk.testing.processes import FakeProcesses


async def test_close_failure_keeps_handles_until_exit_can_be_joined(
    tmp_path, monkeypatch
):
    child = OwnedChild(FakeProcesses())
    process = SimpleNamespace(returncode=None, wait=AsyncMock(return_value=0))

    class Owner:
        fail = True

        def close(self):
            if self.fail:
                raise OSError("native close failed")

    owner = Owner()
    monkeypatch.setattr(child, "process", process)
    child.owner = owner
    child.log = (tmp_path / "child.log").open("ab")
    with pytest.raises(OSError, match="native close failed"):
        await child.close()
    assert child.process is process and child.owner is owner
    assert not child.log.closed
    process.wait.assert_not_awaited()
    owner.fail = False
    await child.close()
    process.wait.assert_awaited_once()
    assert child.process is None and child.owner is None and child.log is None
