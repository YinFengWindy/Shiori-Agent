"""Bounded messages at the authenticated callback boundary."""

from dataclasses import dataclass

from .config import MAX_TEXT_LENGTH


class CallbackError(ValueError):
    """A caller-visible rejection whose status must not imply acceptance."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass(frozen=True)
class BotMessage:
    """A Bot message identifies content and a parent, never a role or permission."""

    message_id: str
    text: str
    reply_to: str = ""

    @classmethod
    def parse(cls, payload: object) -> "BotMessage":
        """Reject unsupported fields instead of passing platform metadata through."""
        if not isinstance(payload, dict) or set(payload) - {
            "message_id",
            "text",
            "reply_to",
        }:
            raise CallbackError(400, "消息字段无效")
        values: dict[str, str] = {}
        for key, limit in (
            ("message_id", 128),
            ("text", MAX_TEXT_LENGTH),
            ("reply_to", 128),
        ):
            value = payload.get(key, "")
            if not isinstance(value, str) or len(value) > limit:
                raise CallbackError(400, "消息字段无效或过长")
            if key != "reply_to" and not value.strip():
                raise CallbackError(400, "消息标识和正文不能为空")
            values[key] = value if key == "text" else value.strip()
        return cls(**values)
