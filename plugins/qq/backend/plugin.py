"""QQ（NapCat）渠道插件入口：校验配置，Bot QQ 号齐备时贡献 ``qq`` 渠道（#363 T5）。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class QQConfigModel(BaseModel):
    """``[plugins.qq]``：值明文存 TOML，支持 ``${ENV}`` 占位符。"""

    bot_uin: str = Field(
        default="",
        title="Bot QQ 号",
        description="NapCat 登录的机器人 QQ 号；留空则不启用 QQ 渠道。",
    )
    ws_uri: str = Field(
        default="",
        title="NapCat WebSocket 地址",
        description="如 ws://localhost:3001；留空沿用 NcatBot 默认值。",
    )
    ws_token: str = Field(
        default="",
        title="NapCat WebSocket 令牌",
        description="NapCat 正向 WebSocket 的 access token；留空沿用 NcatBot 默认值。",
    )
    websocket_open_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        title="连接超时",
        json_schema_extra={"unit": "秒"},
        description="与 NapCat 建立 WebSocket 连接的握手超时。",
    )

    @field_validator("bot_uin", "ws_uri", "ws_token", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str:
        # 宿主已展开 ${ENV}；仍未展开说明变量缺失，按未填写处理。旧配置里的
        # bot_uin 可能是 TOML 整数，这里统一成字符串。
        text = str(value if value is not None else "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Bot QQ 号齐备时贡献渠道；NcatBot 只在渠道启动时才导入和配置。"""
    config = QQConfigModel.model_validate(ctx.config.as_dict())
    if not config.bot_uin:
        return
    from .channel import QQChannel

    ctx.channels.add(
        QQChannel(
            bot_uin=config.bot_uin,
            websocket_open_timeout_seconds=config.websocket_open_timeout_seconds,
            ws_uri=config.ws_uri,
            ws_token=config.ws_token,
        )
    )
