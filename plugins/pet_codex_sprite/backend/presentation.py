"""Short presentation commands; completion belongs to background reports."""

from typing import Any
from shiori_sdk.rpc import RpcCapability
from .provider import SpriteModels


class SpritePresentation:
    """Reject commands until the provider background has subscribed."""

    def __init__(self, models: SpriteModels, rpc: RpcCapability) -> None:
        self.models, self.rpc = models, rpc
        self.ready = False

    async def set_ready(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Track the background's explicit subscription lifetime."""
        value = payload.get("ready")
        if not isinstance(value, bool):
            raise ValueError("presentation.ready 需要 ready 布尔值")
        self.ready = value
        return {"ok": True}

    async def present(self, payload: dict[str, object]) -> dict[str, object]:
        """Accept a command without claiming the requested model is displayed."""
        if not self.ready:
            raise ValueError("精灵呈现后台尚未就绪")
        values: dict[str, Any] = dict(payload)
        for key in ("request_id", "lease_id", "role_id", "model_id", "op"):
            if not isinstance(values.get(key), str) or not values[key].strip():
                raise ValueError(f"呈现命令缺少 {key}")
        if values["op"] not in {"prepare", "show", "update", "action", "close", "hide"}:
            raise ValueError("呈现命令 op 无效")
        if values["op"] == "prepare":
            values.update(
                self.models.presentation(values["role_id"], values["model_id"])
            )
        if not await self.rpc.emit("presentation.command", values):
            self.ready = False
            raise ValueError("精灵呈现后台未接收命令")
        return {"accepted": True}
