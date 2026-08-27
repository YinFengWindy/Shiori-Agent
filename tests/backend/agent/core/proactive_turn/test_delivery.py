from __future__ import annotations

from types import SimpleNamespace

from agent.core.proactive_turn.delivery import (
    resolve_target_transport,
    resolve_target_transports,
)


def _pipeline(
    *,
    session_key: str,
    default_role_id: str = "",
    target_transport_fn=None,
    target_transports_fn=None,
):
    return SimpleNamespace(
        _session_key=session_key,
        _cfg=SimpleNamespace(
            default_role_id=default_role_id,
            default_channel="telegram",
            default_chat_id="global-chat",
        ),
        _target_transport_fn=target_transport_fn,
        _target_transports_fn=target_transports_fn,
        _resolve_target_transport=lambda: resolve_target_transport(
            SimpleNamespace(
                _session_key=session_key,
                _cfg=SimpleNamespace(
                    default_role_id=default_role_id,
                    default_channel="telegram",
                    default_chat_id="global-chat",
                ),
                _target_transport_fn=target_transport_fn,
                _target_transports_fn=None,
            )
        ),
    )


def test_role_target_resolver_failure_does_not_fall_back_to_global_target() -> None:
    def fail() -> tuple[str, str]:
        raise RuntimeError("binding unavailable")

    pipeline = _pipeline(session_key="role:mira", target_transport_fn=fail)

    assert resolve_target_transport(pipeline) is None


def test_role_target_resolver_empty_result_does_not_fall_back_to_global_target() -> None:
    pipeline = _pipeline(
        session_key="role:mira",
        target_transport_fn=lambda: ("", ""),
    )

    assert resolve_target_transport(pipeline) is None


def test_role_transport_list_failure_does_not_fall_back_to_global_target() -> None:
    def fail() -> list[tuple[str, str]]:
        raise RuntimeError("bindings unavailable")

    pipeline = _pipeline(
        session_key="telegram:global",
        default_role_id="mira",
        target_transports_fn=fail,
        target_transport_fn=lambda: ("telegram", "global-chat"),
    )

    assert resolve_target_transports(pipeline) == []


def test_global_target_resolver_failure_can_use_global_fallback() -> None:
    def fail() -> tuple[str, str]:
        raise RuntimeError("binding unavailable")

    pipeline = _pipeline(session_key="telegram:global", target_transport_fn=fail)

    assert resolve_target_transport(pipeline) == ("telegram", "global-chat")
