"""Internal MCP client shared by user MCP, Browser Use and Computer Use."""

from .contracts import (
    McpSession,
    McpToolInfo,
    McpToolError,
    McpProtocolError,
    McpHttpError,
    McpAuthenticationRequired,
)
from .http import HttpMcpSession
from .stdio import StdioMcpSession

__all__ = [
    "McpSession",
    "McpToolInfo",
    "McpToolError",
    "McpProtocolError",
    "McpHttpError",
    "McpAuthenticationRequired",
    "HttpMcpSession",
    "StdioMcpSession",
]
