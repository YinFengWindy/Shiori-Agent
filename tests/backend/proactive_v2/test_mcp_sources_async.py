from __future__ import annotations
from typing import Any, cast

from pathlib import Path

import pytest

from proactive_v2 import mcp_sources


class _FakePool:
    def __init__(
        self,
        responses: dict[tuple[str, str], object],
        failures: set[tuple[str, str]] | None = None,
    ) -> None:
        self._workspace = Path("unused-workspace")
        self._responses = responses
        self._failures = failures or set()
        self.calls: list[tuple[str, str, dict]] = []
        self.timeouts: list[float | None] = []
        self.retry_flags: list[bool] = []

    async def call(
        self,
        server: str,
        tool_name: str,
        args: dict[str, Any],
        *,
        timeout: float | None = None,
        retry_on_transport: bool = False,
    ):
        self.calls.append((server, tool_name, dict(args)))
        self.timeouts.append(timeout)
        self.retry_flags.append(retry_on_transport)
        if (server, tool_name) in self._failures:
            raise RuntimeError(f"failed: {server}.{tool_name}")
        return self._responses[(server, tool_name)]


def test_sync_api_tombstones_raise_migration_error():
    tombstones = [
        (mcp_sources.poll_content_feeds, ()),
        (mcp_sources.fetch_alert_events, ()),
        (mcp_sources.fetch_content_events, ()),
        (mcp_sources.fetch_context_data, ()),
        (mcp_sources.acknowledge_events, ([],)),
        (mcp_sources.acknowledge_content_entries, ([],)),
    ]

    for function, args in tombstones:
        with pytest.raises(RuntimeError, match="mcp_sources.sync API 已移除"):
            function(*args)


@pytest.mark.asyncio
async def test_fetch_alert_events_async_filters_kind_and_sets_ack_server(monkeypatch):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [
            {"channel": "alert", "server": "s1", "get_tool": "get_proactive_events"},
            {"channel": "context", "server": "ctx", "get_tool": "get_context"},
        ],
    )
    pool = _FakePool(
        {
            ("s1", "get_proactive_events"): [
                {"kind": "alert", "event_id": "a1"},
                {"kind": "content", "event_id": "c1"},
            ],
            ("ctx", "get_context"): {"available": True},
        }
    )

    result = await mcp_sources.fetch_alert_events_async(cast(Any, pool))

    assert result == [{"kind": "alert", "event_id": "a1", "ack_server": "s1"}]
    assert pool.retry_flags == [True]


@pytest.mark.asyncio
async def test_fetch_content_events_async_keeps_default_compat_channel_filter(monkeypatch):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [
            {"channel": "", "server": "s1", "get_tool": "get_proactive_events"},
            {"channel": "alert", "server": "alert_only", "get_tool": "get_proactive_events"},
        ],
    )
    pool = _FakePool(
        {
            ("s1", "get_proactive_events"): [
                {"kind": "content", "event_id": "n1"},
                {"kind": "alert", "event_id": "a1"},
            ],
            ("alert_only", "get_proactive_events"): [{"kind": "content", "event_id": "x"}],
        }
    )

    result = await mcp_sources.fetch_content_events_async(cast(Any, pool))

    assert result == [{"kind": "content", "event_id": "n1", "ack_server": "s1"}]


@pytest.mark.asyncio
async def test_fetch_context_data_async_accepts_dict_and_list(monkeypatch, caplog):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [
            {"channel": "context", "server": "ctx1", "get_tool": "get_context"},
            {"channel": "context", "server": "ctx2", "get_tool": "get_context"},
        ],
    )
    pool = _FakePool(
        {
            ("ctx1", "get_context"): {"available": True},
            ("ctx2", "get_context"): [{"available": False}, "bad_item"],
        }
    )

    result = await mcp_sources.fetch_context_data_async(cast(Any, pool))

    assert result == [
        {"available": True, "_source": "ctx1"},
        {"available": False, "_source": "ctx2"},
    ]
    assert "ctx2" in caplog.text
    assert "1 个非法条目" in caplog.text
    assert pool.retry_flags == [True, True]


@pytest.mark.asyncio
async def test_fetch_context_data_async_isolates_invalid_top_level_source(monkeypatch, caplog):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [
            {"channel": "context", "server": "invalid", "get_tool": "get_context"},
            {"channel": "context", "server": "valid", "get_tool": "get_context"},
        ],
    )
    pool = _FakePool(
        {
            ("invalid", "get_context"): "not-an-object",
            ("valid", "get_context"): {"available": True},
        }
    )

    result = await mcp_sources.fetch_context_data_async(cast(Any, pool))

    assert result == [{"available": True, "_source": "valid"}]
    assert "invalid" in caplog.text
    assert "unsupported payload type str" in caplog.text
    assert pool.retry_flags == [True, True]


@pytest.mark.asyncio
async def test_poll_content_feeds_async_raises_when_any_source_failed(monkeypatch):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [
            {"channel": "content", "server": "s1", "poll_tool": "poll"},
            {"channel": "content", "server": "s2", "poll_tool": "poll"},
            {"channel": "alert", "server": "a1", "poll_tool": "poll"},
        ],
    )
    pool = _FakePool(
        {
            ("s1", "poll"): {"ok": True},
            ("s2", "poll"): {"ok": True},
            ("a1", "poll"): {"ok": True},
        },
        failures={("s2", "poll")},
    )

    with pytest.raises(RuntimeError) as exc:
        await mcp_sources.poll_content_feeds_async(cast(Any, pool))

    assert "s2" in str(exc.value)
    assert ("a1", "poll", {}) not in pool.calls
    assert pool.timeouts == [mcp_sources._POLL_TOOL_TIMEOUT, mcp_sources._POLL_TOOL_TIMEOUT]
    assert pool.retry_flags == [False, False]


@pytest.mark.asyncio
async def test_mcp_pool_disconnects_timeout_client_without_retry():
    class _TimeoutClient:
        def __init__(self) -> None:
            self.disconnected = False
            self.calls = 0

        async def call(
            self,
            tool_name: str,
            args: dict[str, Any],
            *,
            timeout: float | None = None,
        ) -> str:
            self.calls += 1
            raise TimeoutError("slow")

        async def disconnect(self) -> None:
            self.disconnected = True

    pool = mcp_sources.McpClientPool(Path("unused-workspace"))
    client = _TimeoutClient()
    pool._configs["feed"] = (["cmd"], {})
    pool._clients["feed"] = client

    with pytest.raises(TimeoutError):
        await pool.call("feed", "poll_feeds", {}, timeout=1.0)

    assert client.calls == 1
    assert client.disconnected is True
    assert "feed" not in pool._clients


@pytest.mark.asyncio
async def test_mcp_pool_does_not_retry_transport_failure_by_default():
    class _BrokenClient:
        def __init__(self) -> None:
            self.calls = 0
            self.disconnected = False

        async def call(
            self,
            tool_name: str,
            args: dict[str, Any],
            *,
            timeout: float | None = None,
        ) -> str:
            self.calls += 1
            raise ConnectionError("pipe closed")

        async def disconnect(self) -> None:
            self.disconnected = True

    pool = mcp_sources.McpClientPool(Path("unused-workspace"))
    client = _BrokenClient()
    pool._configs["feed"] = (["cmd"], {})
    pool._clients["feed"] = client

    with pytest.raises(ConnectionError, match="pipe closed"):
        await pool.call("feed", "get_proactive_events", {})

    assert client.calls == 1
    assert client.disconnected is True
    assert "feed" not in pool._clients


@pytest.mark.asyncio
async def test_mcp_pool_retries_explicit_read_transport_failure_once():
    class _BrokenClient:
        def __init__(self) -> None:
            self.calls = 0
            self.disconnected = False

        async def call(
            self,
            tool_name: str,
            args: dict[str, Any],
            *,
            timeout: float | None = None,
        ) -> str:
            self.calls += 1
            raise ConnectionError("pipe closed")

        async def disconnect(self) -> None:
            self.disconnected = True

    class _ReadClient:
        def __init__(self) -> None:
            self.calls = 0

        async def call(
            self,
            tool_name: str,
            args: dict[str, Any],
            *,
            timeout: float | None = None,
        ) -> str:
            self.calls += 1
            return '{"available": true}'

        async def disconnect(self) -> None:
            return None

    pool = mcp_sources.McpClientPool(Path("unused-workspace"))
    first = _BrokenClient()
    second = _ReadClient()
    pool._configs["ctx"] = (["cmd"], {})
    pool._clients["ctx"] = first

    async def reconnect(server: str) -> bool:
        pool._clients[server] = second
        return True

    pool._connect = reconnect  # type: ignore[method-assign]

    result = await pool.call(
        "ctx",
        "get_context",
        {},
        retry_on_transport=True,
    )

    assert result == {"available": True}
    assert first.calls == 1
    assert first.disconnected is True
    assert second.calls == 1


@pytest.mark.asyncio
async def test_mcp_pool_does_not_retry_json_rpc_tool_error():
    from agent.mcp.client import McpToolError

    class _ErrorClient:
        def __init__(self) -> None:
            self.calls = 0
            self.disconnected = False

        async def call(
            self,
            tool_name: str,
            args: dict[str, Any],
            *,
            timeout: float | None = None,
        ) -> str:
            self.calls += 1
            raise McpToolError(
                server="ctx",
                tool_name=tool_name,
                message="invalid arguments",
                code=-32602,
                data={"field": "query"},
            )

        async def disconnect(self) -> None:
            self.disconnected = True

    pool = mcp_sources.McpClientPool(Path("unused-workspace"))
    client = _ErrorClient()
    pool._configs["ctx"] = (["cmd"], {})
    pool._clients["ctx"] = client

    with pytest.raises(McpToolError) as exc_info:
        await pool.call("ctx", "get_context", {}, retry_on_transport=True)

    assert exc_info.value.code == -32602
    assert exc_info.value.data == {"field": "query"}
    assert client.calls == 1
    assert client.disconnected is True
    assert "ctx" not in pool._clients


@pytest.mark.asyncio
async def test_acknowledge_events_async_groups_by_ack_server(monkeypatch):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [
            {"server": "fitbit", "ack_tool": "ack_events"},
            {"server": "feed", "ack_tool": "ack_events"},
        ],
    )
    pool = _FakePool(
        {
            ("fitbit", "ack_events"): {"ok": True},
            ("feed", "ack_events"): {"ok": True},
        }
    )

    class _Evt:
        def __init__(self, ack_server, ack_id, source_name=""):
            self._ack_server = ack_server
            self.ack_id = ack_id
            self.source_name = source_name

    events = [
        _Evt("fitbit", "a1"),
        _Evt("fitbit", "a2"),
        _Evt("", "a3", source_name="feed"),
        _Evt("unknown", "x"),
    ]
    await mcp_sources.acknowledge_events_async(cast(Any, pool), events)

    assert ("fitbit", "ack_events", {"event_ids": ["a1", "a2"]}) in pool.calls
    assert ("feed", "ack_events", {"event_ids": ["a3"]}) in pool.calls
    assert pool.retry_flags == [False, False]


@pytest.mark.asyncio
async def test_acknowledge_content_entries_async_passes_ttl_hours(monkeypatch):
    monkeypatch.setattr(
        mcp_sources,
        "_load_sources",
        lambda _w=None: [{"server": "feed", "ack_tool": "ack_content"}],
    )
    pool = _FakePool({("feed", "ack_content"): {"ok": True}})

    entries = [
        ("mcp:feed:evt-1", "fallback-1"),
        ("mcp:feed", "evt-2"),
        ("rss:other", "skip"),
    ]
    await mcp_sources.acknowledge_content_entries_async(cast(Any, pool), entries, ttl_hours=24)

    assert (
        "feed",
        "ack_content",
        {"event_ids": ["evt-1", "evt-2"], "ttl_hours": 24},
    ) in pool.calls
    assert pool.retry_flags == [False]
