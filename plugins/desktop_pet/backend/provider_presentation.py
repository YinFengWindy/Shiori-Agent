"""Short presentation transport shared by independent model providers."""

from collections.abc import Callable
from typing import Any

from shiori_sdk.rpc import RpcCapability


class ProviderPresentation:
    """Accept commands only after subscription; completion stays with the renderer."""

    def __init__(
        self,
        rpc: RpcCapability,
        prepare: Callable[[str, str], dict[str, Any]],
        *,
        label: str,
    ) -> None:
        self.rpc, self.prepare, self.label = rpc, prepare, label
        self.ready = False

    async def set_ready(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Track the owning background's explicit subscription lifetime."""
        ready = payload.get("ready")
        if not isinstance(ready, bool):
            raise ValueError("presentation.ready 需要 ready 布尔值")
        self.ready = ready
        return {"ok": True}

    async def present(self, payload: dict[str, object]) -> dict[str, object]:
        """Resolve trusted preparation data without claiming the model is displayed."""
        if not self.ready:
            raise ValueError(f"{self.label}呈现后台尚未就绪")
        values: dict[str, Any] = dict(payload)
        for key in ("request_id", "lease_id", "role_id", "model_id", "op"):
            if not isinstance(values.get(key), str) or not values[key].strip():
                raise ValueError(f"呈现命令缺少 {key}")
        if values["op"] not in {"prepare", "show", "hide", "update", "action", "close"}:
            raise ValueError("呈现命令 op 无效")
        if values["op"] == "prepare":
            values.update(self.prepare(values["role_id"], values["model_id"]))
        if not await self.rpc.emit("presentation.command", values):
            self.ready = False
            raise ValueError(f"{self.label}呈现后台未接收命令")
        return {"accepted": True}
