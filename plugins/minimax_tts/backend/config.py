"""Provider-owned credentials and settings."""

from pydantic import BaseModel, Field


class MiniMaxTtsConfig(BaseModel):
    """Validated settings in [plugins.minimax_tts]."""

    base_url: str = Field(
        default="https://api.minimaxi.com/v1/t2a_v2", title="服务地址"
    )
    model: str = Field(default="speech-2.8-turbo", title="模型")
    api_key: str = Field(
        default="", title="API Key", json_schema_extra={"secret": True}
    )
    volume: float = Field(default=2.0, title="音量", ge=0.1, le=10.0)
