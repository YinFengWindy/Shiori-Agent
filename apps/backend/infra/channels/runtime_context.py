"""Host-only control services layered on the public transport context."""

from dataclasses import dataclass

from agent.tools.message_push import MessagePushTool
from shiori_sdk.channels import ChannelContext


@dataclass
class RuntimeChannelContext(ChannelContext):
    """The coordinator may retire senders; plugins only consume the SDK sender surface."""

    push_tool: MessagePushTool
