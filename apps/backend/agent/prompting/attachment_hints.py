"""Provenance for attachment instructions created by the message envelope owner."""

# Transient render metadata; provider normalization removes it before budgeting
# or transport. User-supplied text cannot create this message-level record.
ATTACHMENT_TOOL_HINTS_KEY = "_shiori_attachment_tool_hints"


def without_attachment_tool_hints(message: dict) -> dict:
    """Remove only recorded generated lines, preserving look-alike user prose."""
    record = message.get(ATTACHMENT_TOOL_HINTS_KEY)
    if record is None:
        return message
    result = {
        key: value for key, value in message.items() if key != ATTACHMENT_TOOL_HINTS_KEY
    }
    content = message["content"]
    part_index = record["part"]
    text = content if part_index is None else content[part_index]["text"]
    # Exact spans come from the append site, not from matching user text.
    # Reverse order keeps earlier recorded positions stable during removal.
    for start, end, generated in reversed(record["spans"]):
        if text[start:end] != generated:
            raise ValueError("附件提示来源记录与消息正文不一致")
        text = text[:start] + text[end:]
    if part_index is None:
        result["content"] = text
    else:
        parts = list(content)
        parts[part_index] = {**parts[part_index], "text": text}
        result["content"] = parts
    return result


def prepare_attachment_hints(messages: list[dict], *, tools_enabled: bool) -> None:
    """Remove generated reader instructions when this exact request has no tools."""
    if not tools_enabled:
        messages[:] = [without_attachment_tool_hints(message) for message in messages]
