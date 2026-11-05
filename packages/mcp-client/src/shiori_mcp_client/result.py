"""Pure MCP result conversion shared by the library transports."""

import base64
import binascii
import json
from typing import Any
from mcp_types import CallToolResult

from shiori_sdk.tools import ToolResult


from .contracts import McpToolError


def decode_tool_result(
    server: str, tool_name: str, response: dict[str, Any]
) -> str | ToolResult:
    """Preserves text compatibility and turns inline MCP images into model content."""
    if "error" in response:
        error = response["error"]
        details = error if isinstance(error, dict) else {"message": str(error)}
        raw_code = details.get("code")
        raise McpToolError(
            server=server,
            tool_name=tool_name,
            message=str(details.get("message", details)),
            code=raw_code if isinstance(raw_code, int) else None,
            data=details.get("data"),
        )
    result = response.get("result", {})
    texts: list[str] = []
    images: list[dict[str, Any]] = []
    for block in result.get("content", []):
        kind = block.get("type", "text")
        if kind == "text":
            texts.append(block.get("text", ""))
        elif kind == "image":
            mime, data = block.get("mimeType", ""), block.get("data", "")
            if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                raise ValueError(f"Unsupported MCP image MIME: {mime!r}")
            try:
                if not base64.b64decode(data, validate=True):
                    raise ValueError("Empty MCP image")
            except (binascii.Error, TypeError) as exc:
                raise ValueError("Invalid MCP image base64") from exc
            images.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{data}"},
                }
            )
        else:
            texts.append(str(block))
    structured = result.get("structuredContent")
    if structured is not None:
        if not isinstance(structured, dict):
            raise ValueError("MCP structuredContent must be an object")
        # Snapshot handles and target identity often exist only here. Keep them
        # visible to the current model as well as available to owning adapters.
        texts.append(json.dumps(structured, ensure_ascii=False))
    text = "\n".join(texts)
    if result.get("isError"):
        raise McpToolError(
            server=server, tool_name=tool_name, message=text or "Remote tool failed"
        )
    if images or structured is not None:
        return ToolResult(
            text=text, content_blocks=images, structured_content=structured
        )
    return text


def result_payload(result: CallToolResult) -> dict[str, Any]:
    """Preserve modern JSON values as text without changing ToolResult's object contract."""
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    if "structured_content" in result.model_fields_set and not isinstance(
        result.structured_content, dict
    ):
        value = result.structured_content
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        content = payload.setdefault("content", [])
        equivalent = False
        for block in content:
            if block.get("type") == "text":
                try:
                    # Compare JSON representations, so True and 1 remain different.
                    equivalent = (
                        json.dumps(
                            json.loads(block["text"]),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        == text
                    )
                except (ValueError, TypeError, KeyError):
                    continue
                if equivalent:
                    break
        if not equivalent:
            content.append({"type": "text", "text": text})
        payload.pop("structuredContent", None)
    return payload
