"""Keeps exact observation identities; never resolves an implicit active window."""

import base64
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from uuid import uuid4

from PIL import Image
from agent.tools.base import ToolResult

from .windows import TargetError, WindowIdentity, inspect_window


@dataclass
class Observation:
    """One Driver snapshot and its exact host-validated physical target."""

    identity: WindowIdentity
    observation_id: str
    snapshot_id: str
    tokens: set[str]
    image_size: tuple[int, int] | None


class WindowTargets:
    """Rejects stale handles, ambiguous routing and unsupported coordinate spaces."""

    def __init__(self) -> None:
        self._observations: dict[tuple[int, int], Observation] = {}

    def validate(self, name: str, arguments: dict[str, Any]) -> WindowIdentity | None:
        """Validates the target immediately before a serialized native action."""
        if name == "list_windows":
            return None
        pid, window_id = arguments.get("pid"), arguments.get("window_id")
        if (
            type(pid) is not int
            or type(window_id) is not int
            or pid <= 0
            or window_id <= 0
        ):
            raise TargetError("必须显式传入 list_windows 返回的 pid 和 window_id")
        identity = inspect_window(pid, window_id)
        if name == "get_window_state":
            return identity
        observed = self._observations.get((pid, window_id))
        if observed is None or observed.identity != identity:
            raise TargetError("窗口身份、位置或缩放已变化，请重新 get_window_state")
        if arguments.get("snapshot_id") != observed.snapshot_id:
            raise TargetError("snapshot_id 已失效，请重新 get_window_state")
        if arguments.get("observation_id") != observed.observation_id:
            raise TargetError("observation_id 已失效，请重新 get_window_state")
        token = arguments.get("element_token")
        if token is not None and token not in observed.tokens:
            raise TargetError("element_token 已失效或不属于此窗口")
        if "element_index" in arguments and not token:
            raise TargetError("控件操作必须使用本次 snapshot 的 element_token")
        if (
            name == "hotkey" or (name == "press_key" and arguments.get("modifiers"))
        ) and arguments.get("delivery_mode") != "foreground":
            # v0.28.2 posted modifier keys inserted bare text in our native
            # fixture. Refuse before input; never silently retry in foreground.
            raise TargetError(
                "Cua Driver 0.28.2 不支持可靠的后台组合键；请显式选择 delivery_mode=foreground 并验证实际状态"
            )
        x, y = arguments.get("x"), arguments.get("y")
        if (x is None) != (y is None):
            raise TargetError("截图坐标 x 和 y 必须同时提供")
        if x is not None and y is not None:
            size = observed.image_size
            if size is None or not (0 <= x < size[0] and 0 <= y < size[1]):
                raise TargetError("坐标超出当前窗口截图范围")
        return identity

    def remember(self, identity: WindowIdentity, result: str | ToolResult) -> None:
        """Retains Driver tokens without replacing them with local element indices."""
        if not isinstance(result, ToolResult) or result.structured_content is None:
            raise TargetError("Cua Driver 未返回结构化窗口快照")
        data = result.structured_content
        if (
            data.get("pid") != identity.pid
            or data.get("window_id") != identity.window_id
        ):
            raise TargetError("Cua Driver 返回了不同的窗口身份")
        snapshot_id = data.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise TargetError("Cua Driver 快照缺少 snapshot_id")
        tokens = {
            element["element_token"]
            for element in data.get("elements", [])
            if element.get("element_token")
        }
        size = None
        if result.content_blocks:
            encoded = result.content_blocks[0]["image_url"]["url"].split(",", 1)[1]
            with Image.open(BytesIO(base64.b64decode(encoded))) as image:
                size = image.size
        observation_id = uuid4().hex
        # Driver counters restart at s00000001 in each process. The additional
        # host receipt prevents an old token from matching a new generation.
        data["observation_id"] = observation_id
        result.text += f"\nShiori observation_id: {observation_id}"
        self._observations[(identity.pid, identity.window_id)] = Observation(
            identity, observation_id, snapshot_id, tokens, size
        )
