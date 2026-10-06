"""Neutral blocking-worker fixture for production runtime retirement checks."""

import asyncio
import threading


async def setup(ctx):
    """Expose only test barriers; publish normal JSON service calls through the host."""
    state = {
        "started": threading.Event(),
        "release": threading.Event(),
        "accepted": 0,
        "active": 0,
        "maximum": 0,
        "finished": 0,
        "closed": False,
    }
    lock = asyncio.Lock()

    def close():
        state["closed"] = True

    ctx.effect("client", close)

    async def worker():
        async with lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            state["started"].set()
            await asyncio.to_thread(state["release"].wait)
            state["active"] -= 1
            state["finished"] += 1
            return {"finished": state["finished"]}

    async def run(_payload):
        state["accepted"] += 1
        task = ctx.background.spawn_runtime(worker(), name="retained-worker")
        return await asyncio.shield(task)

    ctx.services.register(
        "worker", contract="test.worker.v1", label="Worker", methods={"run": run}
    )
    ctx.expose(state)
