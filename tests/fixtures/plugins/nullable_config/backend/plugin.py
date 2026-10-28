from enum import Enum

from pydantic import BaseModel

from shiori_sdk.core.services import CONFIG


class Mode(Enum):
    """刻意不继承 str：这样 Enum 实例本身无法直接过 json.dumps。"""

    QUIET = "quiet"
    LOUD = "loud"


class NullableConfigModel(BaseModel):
    """两个刁钻默认值：null 在 TOML 里无表达形式，Enum 不能直接过 JSON 传输。"""

    label: str | None = "default-label"
    mode: Mode = Mode.QUIET


async def setup(ctx):
    """Validates the fixture's explicitly declared configuration model."""
    NullableConfigModel.model_validate(ctx.require(CONFIG).as_dict())
