"""Contract-only tool hook registration and dispatch for policy unit tests."""

import inspect
from dataclasses import dataclass
from shiori_sdk.tool_hooks import HookOutcome, PreToolCtx, PreToolHandler


@dataclass
class FakeHook:
    """One plugin registration, with the filter and explicit handler name recorded."""

    handler: PreToolHandler
    tool_name_filter: str | None
    handler_name: str


class FakeToolHooks:
    """Exercise plugin handlers without a host tool executor or LLM runtime."""

    def __init__(self):
        self.handlers: list[FakeHook] = []

    def add_handler(
        self,
        handler: PreToolHandler,
        *,
        tool_name_filter: str | None = None,
        handler_name: str | None = None,
    ) -> None:
        """Record the public registration supplied by setup."""
        self.handlers.append(
            FakeHook(
                handler,
                tool_name_filter,
                handler_name or getattr(handler, "__name__", "handler"),
            )
        )

    async def dispatch(self, event: PreToolCtx) -> HookOutcome:
        """Apply matching handlers and return their observable decision or rewrite."""
        outcome = HookOutcome()
        for entry in self.handlers:
            if (
                entry.tool_name_filter is not None
                and entry.tool_name_filter != event.tool_name
            ):
                continue
            result = entry.handler(event)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict):
                outcome = HookOutcome(updated_input=result)
            elif isinstance(result, HookOutcome):
                outcome = result
            if outcome.updated_input is not None:
                event.arguments = dict(outcome.updated_input)
            if outcome.decision == "deny":
                return outcome
        return outcome
