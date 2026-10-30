"""Affection: relationship, loneliness and the affection state files."""

from __future__ import annotations


from shiori_sdk.core.affection import AFFECTION
from shiori_sdk.core.affection_host import AFFECTION_HOST
from shiori_sdk.core.services import BACKGROUND, RPC
from shiori_sdk.rpc import Concurrency
from shiori_sdk.runtime import PluginRuntimeContext

from .relationship.loops import LonelinessHeartbeatLoop
from .relationship.service import RoleRelationshipRuntimeService

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


def _whole(value: object, default: int) -> int:
    """A JSON page number or size; empty or 0 means ``default``. Non-numbers raise."""
    return int(str(value)) if value else default


class AffectionApi:
    """Plugin RPC the affection page calls."""

    def __init__(self, runtime: RoleRelationshipRuntimeService) -> None:
        self._runtime = runtime

    async def history(self, payload: dict[str, object]) -> dict[str, object]:
        """One newest-first page plus the current summary."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._runtime.sources.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        page = max(1, _whole(payload.get("page"), 1))
        page_size = max(
            1, min(_MAX_PAGE_SIZE, _whole(payload.get("page_size"), _DEFAULT_PAGE_SIZE))
        )
        summary = self._runtime.affection.current_summary(role_id)
        entries, total = self._runtime.affection.history_page(
            role_id, page=page, page_size=page_size
        )
        return {
            "role_id": role_id,
            "affection": summary,
            "items": [{"id": id_, **entry.to_dict()} for id_, entry in entries],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def chat_status(self, payload: dict[str, object]) -> dict[str, object]:
        """The chat sidebar's summary, relationship tags and loneliness."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._runtime.sources.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        return self._runtime.chat_status(role_id)

    async def stage_prompts_get(self, payload: dict[str, object]) -> dict[str, object]:
        """Each stage's injected guidance."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._runtime.sources.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        return {"role_id": role_id, "stages": self._runtime.stage_prompts_view(role_id)}

    async def stage_prompts_set(self, payload: dict[str, object]) -> dict[str, object]:
        """Writes named stages and answers with every stage as stored."""
        changes = payload.get("prompts")
        if not isinstance(changes, dict):
            raise ValueError("prompts 必须是以阶段名为键的对象")
        role_id = str(payload.get("role_id") or "").strip()
        self._runtime.apply_stage_prompts(role_id, changes)
        return {"role_id": role_id, "stages": self._runtime.stage_prompts_view(role_id)}


# Renderer event after a role's sidebar data changed outside a turn
# (``plugin.affection.chat_status.changed``, payload ``{role_id}``).
STATUS_CHANGED_EVENT = "chat_status.changed"


async def setup(ctx: PluginRuntimeContext) -> None:
    """Provides ``AFFECTION``, serves the UI's RPC and starts the heartbeat."""
    rpc = ctx.require(RPC)

    async def status_changed(role_id: str) -> None:
        _ = await rpc.emit(STATUS_CHANGED_EVENT, {"role_id": role_id})

    runtime = RoleRelationshipRuntimeService(
        ctx.require(AFFECTION_HOST), status_changed=status_changed
    )
    ctx.provide(AFFECTION, runtime)
    api = AffectionApi(runtime)
    # Reading the summary settles due decay and loneliness ticks, so the reads
    # that do so write files and stay on the mutation lane.
    rpc.register("history", api.history)
    rpc.register("chat_status", api.chat_status)
    rpc.register(
        "stage_prompts_get", api.stage_prompts_get, concurrency=Concurrency.READ_ONLY
    )
    rpc.register("stage_prompts_set", api.stage_prompts_set)
    loop = LonelinessHeartbeatLoop(runtime)
    task = ctx.require(BACKGROUND).spawn(loop.run(), name="loneliness")

    def stop() -> None:
        loop.stop()
        task.cancel()

    ctx.effect("affection.loneliness", stop)
