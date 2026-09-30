"""Bridge commands behind group listening on the phone (#538): a group's
listening records, its switch and daily cap, and the global default cap."""

from __future__ import annotations

from typing import Any

from conversation.listening import GroupListeningControl
from conversation.listening_store import ListeningMessage
from conversation.listening_switches import ListeningSettings
from conversation.models import ThreadRecord
from desktop_bridge.phone_requests import DesktopPhoneRequestHandler
from desktop_bridge.session_presenter import MESSAGE_PAGE_SIZE

# Bridge event carrying a message newly stored in a group's listening records.
PHONE_LISTENING_HEARD = "phone.listening.heard"


def _listening_row(message: ListeningMessage) -> dict[str, Any]:
    """A listening record in the shape of a stored session message."""
    return {
        "id": message.id,
        "seq": message.seq,
        "role": "user",
        "content": message.content,
        "timestamp": message.timestamp,
        "metadata": {"message_source": message.source},
    }


class DesktopPhoneListeningRequestHandler:
    """Reads group listening and changes it from the phone, as the user.

    Group requests name ``role_id`` and ``thread_id``, one of the role's
    channel conversations (checked by ``phone``, which also builds the
    message rows).

    - ``phone.listening.messages`` with optional ``before_seq`` / ``limit``
      returns a page of the group's listening records like
      ``phone.conversation.messages`` (rows with ``listened``); records stay
      readable after listening is turned off.

    The rest need a group on a channel that supports listening and return the
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

    def __init__(
        self, listening: GroupListeningControl, phone: DesktopPhoneRequestHandler
    ) -> None:
        self._listening = listening
        self._phone = phone

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one listening request; None for methods it does not own."""
        switches = self._listening.store.switches
        if method == "phone.listening.defaults":
            return {"default_daily_cap": switches.default_daily_cap()}
        if method == "phone.listening.defaults.save":
            cap = switches.set_default_daily_cap(payload.get("default_daily_cap"))
            return {"default_daily_cap": cap}
        if method == "phone.listening.messages":
            role_id, thread = self._phone.role_thread(payload)
            before_seq = payload.get("before_seq")
            return self._page(
                role_id,
                thread,
                before_seq=int(before_seq) if before_seq is not None else None,
                limit=int(payload.get("limit") or MESSAGE_PAGE_SIZE),
            )
        if method not in {
            "phone.listening.state",
            "phone.listening.set",
            "phone.listening.cap.set",
        }:
            return None
        role_id, thread = self._phone.role_thread(payload)
        if method == "phone.listening.set":
            enabled = payload.get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError("enabled 必须是布尔值")
            settings = self._listening.set_enabled(
                role_id, thread.id, enabled, operator="user"
            )
        elif method == "phone.listening.cap.set":
            settings = self._listening.set_daily_cap(
                role_id, thread.id, payload.get("daily_cap")
            )
        else:
            settings = switches.settings(self._listening.group(role_id, thread.id).id)
        return self._state(settings)

    def heard_update(self, message: ListeningMessage) -> dict[str, Any] | None:
        """The ``phone.listening.heard`` payload for a newly stored record.

        None when its group is no longer one of its role's conversations.
        """
        thread = self._listening.current_thread(message.thread_id)
        if thread is None:
            return None
        [row] = self._phone.phone_messages(
            thread.role_id, thread, [_listening_row(message)], listened=True
        )
        return {"role_id": thread.role_id, "thread_id": thread.id, "message": row}

    def _page(
        self, role_id: str, thread: ThreadRecord, *, before_seq: int | None, limit: int
    ) -> dict[str, Any]:
        page = self._listening.store.page(thread.id, before_seq=before_seq, limit=limit)
        rows = [_listening_row(message) for message in page["messages"]]
        return {
            "thread_id": thread.id,
            "messages": self._phone.phone_messages(
                role_id, thread, rows, listened=True
            ),
            "has_more": page["has_more"],
            "next_before_seq": page["next_before_seq"],
        }

    def _state(self, settings: ListeningSettings) -> dict[str, Any]:
        switches = self._listening.store.switches
        return {
            "thread_id": settings.thread_id,
            "enabled": settings.enabled,
            "daily_cap": settings.daily_cap,
            "default_daily_cap": switches.default_daily_cap(),
            "toggles": [
                {
                    "enabled": toggle.enabled,
                    "operator": toggle.operator,
                    "at": toggle.at,
                }
                for toggle in switches.toggles(settings.thread_id)
            ],
        }
