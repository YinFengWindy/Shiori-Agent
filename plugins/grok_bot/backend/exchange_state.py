"""Persisted reply-chain budgets and migration from account-wide budgets."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Receipt(BaseModel):
    """Transport state without retaining completed conversation text."""

    model_config = ConfigDict(extra="forbid", strict=True)
    direction: Literal["in", "out"]
    digest: str
    exchange_id: str
    reply_to: str = ""
    state: Literal["queued", "sending", "accepted", "complete", "failed", "uncertain"]
    text: str = ""


class ExchangeBudget(BaseModel):
    """A durable count for one root message and all its correlated replies."""

    model_config = ConfigDict(extra="forbid", strict=True)
    count: int = Field(default=0, ge=0)
    closed: bool = False


class ExchangeState(BaseModel):
    """Whole chains are retained or expired together; pruning cannot reduce counts."""

    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[2] = 2
    exchanges: dict[str, ExchangeBudget] = Field(default_factory=dict)
    messages: dict[str, Receipt] = Field(default_factory=dict)
    last_status: str = ""


class _LegacyState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    exchange_id: str = ""
    count: int = Field(default=0, ge=0)
    last_activity: float = 0.0
    messages: dict[str, Receipt] = Field(default_factory=dict)
    last_status: str = ""


def read_exchange_state(value: object) -> ExchangeState:
    """Migrate complete active legacy graphs, keeping retired/incomplete ones closed."""
    try:
        if isinstance(value, dict) and "version" in value:
            state = ExchangeState.model_validate(value)
            for receipt in state.messages.values():
                if receipt.exchange_id not in state.exchanges:
                    raise ValueError("missing exchange")
            for exchange_id, budget in state.exchanges.items():
                retained = sum(
                    receipt.exchange_id == exchange_id
                    for receipt in state.messages.values()
                )
                if budget.count < retained:
                    raise ValueError("budget smaller than retained messages")
            return state
        legacy = _LegacyState.model_validate(value)
        state = ExchangeState(last_status=legacy.last_status)
        active_count = sum(
            receipt.exchange_id == legacy.exchange_id
            for receipt in legacy.messages.values()
        )
        # Legacy retention pruned individual receipts from retired exchanges.
        # Their original counts cannot be recovered, so never reopen their quota.
        active_complete = active_count == legacy.count
        for message_id, receipt in legacy.messages.items():
            root = message_id
            visited: set[str] = set()
            closed = not active_complete or receipt.exchange_id != legacy.exchange_id
            ancestor = receipt
            while ancestor.reply_to:
                if root in visited:
                    raise ValueError("cyclic reply graph")
                visited.add(root)
                root = ancestor.reply_to
                parent = legacy.messages.get(root)
                if parent is None:
                    closed = True
                    break
                if parent.exchange_id != receipt.exchange_id:
                    raise ValueError("cross-exchange reply")
                ancestor = parent
            budget = state.exchanges.setdefault(root, ExchangeBudget())
            budget.count += 1
            budget.closed |= closed
            state.messages[message_id] = receipt.model_copy(
                update={"exchange_id": root}
            )
        return state
    except (ValidationError, ValueError):
        raise ValueError("Grok 对话状态无效，不能安全恢复") from None
