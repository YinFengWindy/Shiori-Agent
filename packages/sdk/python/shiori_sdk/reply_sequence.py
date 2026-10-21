"""Opt-in presentation contract for complete, separately delivered messages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplySequencePolicy:
    """Buffer a reply and honor model-authored separator lines outside code fences.

    The plugin supplies the same separator in its prompt. The host owns parsing,
    pacing, persistence and cancellation; plugins never send the parts themselves.
    """

    separator: str

    def __post_init__(self) -> None:
        if (
            not self.separator
            or self.separator != self.separator.strip()
            or "\n" in self.separator
            or "\r" in self.separator
            or self.separator.startswith(("```", "~~~"))
        ):
            raise ValueError("消息分隔符必须是非空的独立单行标记")
