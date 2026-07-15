"""AgentLoop 流式事件适配。"""

from __future__ import annotations

from bus.events_lifecycle import (
    StreamDeltaReady,
)

from .helpers import (
    StreamDelta,
    StreamSink,
    StreamSinkFactory,
    _suppresses_stream_events,
    _supports_stream_events,
)

class _StreamingMixin:
    def set_stream_sink_factory(self, factory: StreamSinkFactory | None) -> None:
        setter = getattr(self._reasoner, "set_stream_sink_factory", None)
        if callable(setter):
            _ = setter(self._wrap_stream_sink_factory(factory))

    def _configure_stream_events(self) -> None:
        setter = getattr(self._reasoner, "set_stream_sink_factory", None)
        if callable(setter):
            _ = setter(self._build_stream_event_sink)

    def _wrap_stream_sink_factory(
        self,
        factory: StreamSinkFactory | None,
    ) -> StreamSinkFactory | None:
        if factory is None:
            return None

        def _build(msg: object) -> StreamSink | None:
            if _suppresses_stream_events(msg):
                return None
            downstream = factory(msg)
            channel = str(getattr(msg, "channel", ""))
            chat_id = str(getattr(msg, "chat_id", ""))
            session_key = str(getattr(msg, "session_key", f"{channel}:{chat_id}"))
            if downstream is None:
                return None

            async def _push(delta: StreamDelta) -> None:
                if isinstance(delta, str):
                    payload = {"content_delta": delta}
                else:
                    payload = delta
                content_delta = payload.get("content_delta")
                if isinstance(content_delta, str) and content_delta:
                    self._append_partial_reply(session_key, content_delta)
                thinking_delta = payload.get("thinking_delta")
                if isinstance(thinking_delta, str) and thinking_delta:
                    self._append_partial_thinking(session_key, thinking_delta)
                await downstream(payload)

            return _push

        return _build

    def _build_stream_event_sink(self, msg: object) -> StreamSink | None:
        channel = str(getattr(msg, "channel", ""))
        chat_id = str(getattr(msg, "chat_id", ""))
        if _suppresses_stream_events(msg):
            return None
        if not _supports_stream_events(channel, chat_id):
            return None
        session_key = str(getattr(msg, "session_key", f"{channel}:{chat_id}"))

        async def _push(delta: StreamDelta) -> None:
            if isinstance(delta, str):
                payload = {"content_delta": delta}
            else:
                payload = delta
            content_delta = payload.get("content_delta")
            if isinstance(content_delta, str) and content_delta:
                self._append_partial_reply(session_key, content_delta)
            thinking_delta = payload.get("thinking_delta")
            if isinstance(thinking_delta, str) and thinking_delta:
                self._append_partial_thinking(session_key, thinking_delta)
            await self._event_bus.observe(
                StreamDeltaReady(
                    session_key=session_key,
                    channel=channel,
                    chat_id=chat_id,
                    content_delta=(
                        content_delta if isinstance(content_delta, str) else ""
                    ),
                    thinking_delta=(
                        thinking_delta if isinstance(thinking_delta, str) else ""
                    ),
                )
            )

        return _push

    def _append_partial_reply(self, session_key: str, delta: str) -> None:
        state = self._active_turn_states.get(session_key)
        if state is None or not delta:
            return
        state.partial_reply += delta

    def _append_partial_thinking(self, session_key: str, delta: str) -> None:
        state = self._active_turn_states.get(session_key)
        if state is None or not delta:
            return
        state.partial_thinking = (state.partial_thinking or "") + delta
