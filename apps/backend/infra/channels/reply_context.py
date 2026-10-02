"""Host imports of the single SDK message-source contract."""

from shiori_sdk.channels.reply_context import (
    SELF_REPLY_SENDER_LABEL as SELF_REPLY_SENDER_LABEL,
)
from shiori_sdk.channels.reply_context import (
    QUOTED_IMAGE_PLACEHOLDER as QUOTED_IMAGE_PLACEHOLDER,
)
from shiori_sdk.channels.reply_context import (
    build_inbound_text_with_reply_context as build_inbound_text_with_reply_context,
)
from shiori_sdk.channels.reply_context import with_reply_quote as with_reply_quote
