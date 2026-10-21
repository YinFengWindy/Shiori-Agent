"""The single transport consumer selects a configuration for each new task."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bootstrap.runtime.generations import RuntimeLease

from core.common.runtime_scope import bind_runtime, current_runtime_lease
from agent.turns.channel_sequence import channel_reply_scope
from agent.turns.reply_interruption import ReplyInterruption, reply_interruption_scope
from bus.events import SpawnCompletionItem
from shiori_sdk.channels.chat_types import is_group_chat_type
from shiori_sdk.messages import InboundMessage

if TYPE_CHECKING:
    from bootstrap.app import AppRuntime


class RuntimeDispatcher:
    """Routes scheduled and channel work while retaining generation ownership."""

    def __init__(self, app: AppRuntime) -> None:
        self._app = app

    async def run(self) -> None:
        """Preserve each chat's order without serializing unrelated pacing waits.

        The role runtime still owns generation/state serialization. Each accepted
        item retains its admission lease, including while waiting behind its chat.
        """
        pending: set[RuntimeLease] = set()
        tails: dict[tuple[str, ...], asyncio.Task] = {}
        accepted: set[tuple[str, ...]] = set()
        try:
            async with asyncio.TaskGroup() as group:
                while True:
                    item = await self._app.bus.consume_inbound()
                    inherited = item.runtime_lease
                    if inherited is not None and not isinstance(
                        inherited, RuntimeLease
                    ):
                        raise TypeError(
                            "Inbound runtime ownership must be supplied by the host"
                        )
                    if inherited is None:
                        await self._app.wait_for_admission()
                    lease = inherited or self._app.acquire()
                    pending.add(lease)
                    origin = (
                        item
                        if isinstance(item, InboundMessage)
                        else (
                            item.origin
                            if isinstance(item, SpawnCompletionItem)
                            else None
                        )
                    )
                    key = (
                        channel_reply_scope(origin)
                        if origin is not None
                        else (item.session_key, item.channel, item.chat_id)
                    )
                    message_id = str(
                        getattr(item, "metadata", {}).get("external_message_id") or ""
                    )
                    dedupe = (*key, message_id) if message_id else None
                    if getattr(item, "metadata", {}).get("conversation_duplicate") or (
                        dedupe is not None and dedupe in accepted
                    ):
                        await lease.release()
                        pending.discard(lease)
                        continue
                    if dedupe is not None:
                        accepted.add(dedupe)
                    interruption = None
                    background = ()
                    if (
                        origin is not None
                        and origin.metadata.get("role_id")
                        and (
                            origin.channel == "desktop"
                            or self._app.bus.supports_reply_sequence(origin.channel)
                        )
                    ):
                        role = (
                            lease.core.role_runtime_registry.repository.store.get_role(
                                str(origin.metadata["role_id"])
                            )
                        )
                        if role is None:
                            # A role may be removed after its channel accepted
                            # input. Retire that input without stopping other chats.
                            await lease.release()
                            pending.discard(lease)
                            if dedupe is not None:
                                accepted.discard(dedupe)
                            continue
                        if role.runtime_config.get("natural_chat_enabled") is True:
                            background = lease.reply_sequences.background_tasks(origin)
                            interruption = (
                                lease.reply_sequences.admit(item)
                                if isinstance(item, InboundMessage)
                                else ReplyInterruption()
                            )
                    task = group.create_task(
                        self._process_inbound(
                            item,
                            lease,
                            tails.get(key),
                            pending,
                            interruption,
                            background,
                        )
                    )
                    tails[key] = task
                    task.add_done_callback(
                        lambda done, key=key: self._forget_tail(tails, key, done)
                    )
                    if dedupe is not None:
                        task.add_done_callback(
                            lambda _, dedupe=dedupe: accepted.discard(dedupe)
                        )
                    if interruption is not None and isinstance(item, InboundMessage):
                        task.add_done_callback(
                            lambda _, item=item, owner=lease.reply_sequences, reply=interruption: owner.forget(
                                item, reply
                            )
                        )
                    elif interruption is not None and origin is not None:
                        registration = lease.reply_sequences.register_background(
                            origin,
                            interruption,
                            task,
                            senders=(
                                frozenset({origin.sender})
                                if is_group_chat_type(origin.metadata.get("chat_type"))
                                else None
                            ),
                        )
                        task.add_done_callback(
                            lambda _, owner=lease.reply_sequences, reply=registration: owner.forget_background(
                                reply
                            )
                        )
        finally:
            # Tasks cancelled before their first step never entered their lease.
            for lease in pending:
                await lease.release()

    @staticmethod
    def _forget_tail(tails, key, task) -> None:
        if tails.get(key) is task:
            tails.pop(key)

    async def _process_inbound(
        self,
        item,
        lease: RuntimeLease,
        previous: asyncio.Task | None,
        pending: set[RuntimeLease],
        interruption=None,
        background=(),
    ) -> None:
        async with lease:
            pending.discard(lease)
            if previous is not None:
                await asyncio.shield(asyncio.gather(previous, return_exceptions=True))
            if background:
                await asyncio.shield(
                    asyncio.gather(*background, return_exceptions=True)
                )
            bus = self._app.bus
            assert bus is not None
            try:
                with (
                    bind_runtime(lease),
                    lease.reply_sequences.bind(bus),
                    reply_interruption_scope(interruption),
                ):
                    await lease.core.loop.process_inbound(item)
            finally:
                if interruption is not None and isinstance(item, InboundMessage):
                    lease.reply_sequences.forget(item, interruption)

    async def process_direct(self, *args, **kwargs):
        """Keeps scheduled child turns on their parent operation's runtime."""
        current = current_runtime_lease()
        if current is not None:
            return await current.core.loop.process_direct(*args, **kwargs)
        await self._app.wait_for_admission()
        async with self._app.acquire() as lease:
            with bind_runtime(lease):
                return await lease.core.loop.process_direct(*args, **kwargs)

    async def run_role_operation(self, metadata, operation):
        """Pins the complete scheduled operation, including its child turns."""
        await self._app.wait_for_admission()
        async with self._app.acquire() as lease:
            with bind_runtime(lease):
                return await lease.core.loop.run_role_operation(metadata, operation)

    async def process_background_result(self, context, admit) -> None:
        """Select the current generation only for this short result turn."""
        await self._app.wait_for_admission()
        async with self._app.acquire() as lease:
            with bind_runtime(lease), lease.reply_sequences.bind(self._app.bus):
                await lease.core.loop.process_background_result(context, admit)

    def request_interrupt(
        self,
        session_key: str,
        sender: str = "",
        command: str = "/stop",
        *,
        channel: str = "",
        chat_id: str = "",
        account_id: str = "",
        chat_type: str = "",
        message_thread_id: str = "",
    ):
        """Cancels the original task through the shared interrupt registry."""
        return self._app.agent_loop.request_interrupt(
            session_key,
            sender,
            command,
            channel=channel,
            chat_id=chat_id,
            account_id=account_id,
            chat_type=chat_type,
            message_thread_id=message_thread_id,
        )

    def discard_interrupt_state(self, session_key, state):
        """Removes a durably saved interrupt snapshot from shared state."""
        self._app.agent_loop.discard_interrupt_state(session_key, state)
