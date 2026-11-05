# Shiori MCP client

Internal Python distribution for the MCP, Browser Use and Computer Use plugins. It owns MCP protocol sessions, discovery, tool calls, result conversion and cancellation using pinned `mcp==2.3.0`. The host provides only generic process ownership through `Processes.spawn`; the library imports no host or plugin implementations.

```python
from shiori_mcp_client import StdioMcpSession, HttpMcpSession

stdio = StdioMcpSession("docs", ["python", "server.py"], processes=processes,
                        own_process_tree=sys.platform == "win32")
http = HttpMcpSession("docs", "https://example.org/mcp", headers=headers, auth=provider)
try:
    tools = await http.connect()
    result = await http.call("search", {"q": "example"}, timeout=30)
finally:
    await http.disconnect()
```

`auth` is an optional caller-owned `httpx2.Auth`; only the plugin decides whether interactive login is allowed. `connect_timeout` applies to readiness, not session lifetime. Calls use a total deadline including the send queue and never replay automatically. Cancellation may await the official SDK's bounded courtesy notification cleanup. Each supervisor enters and exits its own SDK contexts. Stdio uses chunked framing with a 20 MiB frame limit and closes the supplied process owner before reaping the process.

`McpToolError` preserves remote protocol error data; application boundaries must redact their known credentials. SDK/HTTP diagnostics retain metadata only. `McpHttpError` identifies HTTP rejection; `McpAuthenticationRequired` preserves explicit login-required intent, including nested exception groups. Generic `ToolResult` remains in `shiori-sdk`; images preserve MIME/base64 and structured objects retain `structured_content`. HTTP modern non-object structured values become JSON text without repeating equivalent existing text; stdio retains its object-only structured-result validation.

Local stream closure is observed separately from JSON-RPC errors, so remote `-32000`/`-32001` errors remain tool errors even when the peer immediately closes afterward. The outer deadline is the only tool-call timer. The official HTTP SDK can synthesize an error response for an abandoned HTTP request without exposing its origin; such ambiguous errors conservatively remain `McpToolError` and never authorize the proactive source retry.

The distribution is built into the private wheelhouse, never resolved by name from a public index. Root development installs the local editable source; plugin isolation installs exact wheels and audits installed bytes. Frozen desktops collect the internal library and its declared dependency metadata. This does not add a dependency installer to older desktops or make arbitrary plugin ZIP Python dependencies independently installable.

Run focused protocol checks with `uv run python -m scripts.verify_mcp_client`; run plugin consumers with `uv run python -m scripts.verify_plugin_tests --plugins mcp browser_use computer_use`.
