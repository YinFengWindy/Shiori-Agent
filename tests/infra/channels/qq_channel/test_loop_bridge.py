from __future__ import annotations

import pytest

from infra.channels.qq_channel.loop_bridge import _LoopBridgeMixin


class _Bridge(_LoopBridgeMixin):
    _main_loop = None
    _bot_loop = None


def test_loop_bridge_requires_main_loop_before_cross_loop_submission() -> None:
    with pytest.raises(RuntimeError, match="main loop 未就绪"):
        _Bridge()._require_main_loop()


@pytest.mark.asyncio
async def test_loop_bridge_requires_bot_loop_before_outbound_submission() -> None:
    async def _pending() -> object:
        return None

    pending = _pending()
    try:
        with pytest.raises(RuntimeError, match="bot loop 未就绪"):
            await _Bridge()._run_on_bot_loop(pending)
    finally:
        pending.close()
