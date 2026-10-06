"""Provider-owned credentials and settings."""

from pydantic import BaseModel, Field


class TencentAsrConfig(BaseModel):
    """Validated settings in [plugins.tencent_asr]."""

    base_url: str = Field(default="https://asr.tencentcloudapi.com/", title="服务地址")
    secret_id: str = Field(default="", title="Secret ID")
    secret_key: str = Field(
        default="", title="Secret Key", json_schema_extra={"secret": True}
    )
