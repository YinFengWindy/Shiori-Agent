"""Bridge commands behind the phone's 旁听 block and settings (#538): the
listening switch and daily cap of one group, and the global default cap."""

from __future__ import annotations

from typing import Any

from conversation.listening import GroupListeningControl
from conversation.listening_store import ListeningSettings
from desktop_bridge.phone_requests import required_text


def _cap(value: object) -> int:
    """A cap from a request; the store checks its range."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("每日入库上限必须是整数")
    return value


class DesktopPhoneListeningRequestHandler:
    """Reads and changes group listening from the phone, as the user.

    Group requests name ``role_id`` and ``thread_id``, which must be one of the
    role's groups on a channel that supports listening; each returns the
    group's state: ``enabled``, ``daily_cap`` (the group's override, None
    when it follows the default), ``default_daily_cap`` and ``toggles`` (the
    newest switch changes first, each ``{enabled, operator, at}``).

    - ``phone.listening.state`` reads it.
    - ``phone.listening.set`` with ``enabled`` turns listening on or off;
      the change is logged with the user as operator.
    - ``phone.listening.cap.set`` with ``daily_cap`` (an integer of at least
      1, or None for the default) overrides the group's daily cap.

    ``phone.listening.defaults`` returns ``{"default_daily_cap"}``;
    ``phone.listening.defaults.save`` with ``default_daily_cap`` sets it.
    """

    def __init__(self, listening: GroupListeningControl) -> None:
        self._listening = listening

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one listening request; None for methods it does not own."""
        store = self._listening.store
        if method == "phone.listening.defaults":
            return {"default_daily_cap": store.default_daily_cap()}
        if method == "phone.listening.defaults.save":
            cap = _cap(payload.get("default_daily_cap"))
            return {"default_daily_cap": store.set_default_daily_cap(cap)}
        if method not in {
            "phone.listening.state",
            "phone.listening.set",
            "phone.listening.cap.set",
        }:
            return None
        role_id = required_text(payload, "role_id")
        thread_id = required_text(payload, "thread_id")
        if method == "phone.listening.set":
            enabled = payload.get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError("enabled 必须是布尔值")
            settings = self._listening.set_enabled(
                role_id, thread_id, enabled, operator="user"
            )
        elif method == "phone.listening.cap.set":
            raw = payload.get("daily_cap")
            settings = self._listening.set_daily_cap(
                role_id, thread_id, None if raw is None else _cap(raw)
            )
        else:
            settings = store.settings(self._listening.group(role_id, thread_id).id)
        return self._state(settings)

    def _state(self, settings: ListeningSettings) -> dict[str, Any]:
        store = self._listening.store
        return {
            "thread_id": settings.thread_id,
            "enabled": settings.enabled,
            "daily_cap": settings.daily_cap,
            "default_daily_cap": store.default_daily_cap(),
            "toggles": [
                {
                    "enabled": toggle.enabled,
                    "operator": toggle.operator,
                    "at": toggle.at,
                }
                for toggle in store.toggles(settings.thread_id)
            ],
        }
