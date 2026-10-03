"""Fold bounded source batches into working state independently of semantic memory."""

from __future__ import annotations
from dataclasses import replace
import json
from typing import TYPE_CHECKING, Any
from core.compaction_summary_request import SummaryRequest
from core.compaction_summary_sources import summary_source, shrink_summary_source
from core.compaction_summary_validation import (
    SUMMARY_TOKEN_LIMIT,
    WorkingSummary,
    SummaryAttempt,
    SummaryGenerationError,
    normalize_summary,
    summary_attempt,
    validate_summary_limit,
)
from session.maintenance_progress import window_key
from session.manager.helpers import _TOOL_RESULT_CHAR_BUDGET

if TYPE_CHECKING:
    from agent.provider import LLMProvider
    from session.manager import SessionManager
    from session.manager.window import WindowPreparation

# Below this a message no longer carries usable content; fail instead of shrinking.
_MIN_TEXT_CHARS = 200


def validate_summary(
    content: str, allowed_ids: set[str], limit: int = SUMMARY_TOKEN_LIMIT
) -> WorkingSummary:
    """Validate standalone text using an explicitly local normalized estimate."""
    validate_summary_limit(limit)
    return normalize_summary(content, allowed_ids, summary_attempt(limit, None))


class WorkingSummaryWriter:
    """Fold removed messages into one bounded state within the auxiliary budget."""

    def __init__(
        self,
        sessions: SessionManager,
        provider: LLMProvider,
        model: str,
        max_tokens: int,
        summary_token_limit: int = SUMMARY_TOKEN_LIMIT,
    ) -> None:
        self.sessions = sessions
        self.request = SummaryRequest(provider, model, max_tokens, summary_token_limit)

    @property
    def model_name(self) -> str:
        """Resolve diagnostics through the same provider routing as the request."""
        return self.request.provider.context_model(self.request.model)

    async def generate(self, prepared: WindowPreparation) -> WorkingSummary:
        """Rewrite old valid state together with exactly the newly removed raw range.

        A range that fits the request budget is rewritten in one call. Larger ranges
        are cut into consecutive batches; each batch rewrites the state produced by
        the previous one, so the result stays within the summary hard limit.
        """
        session = self.sessions.get_or_create(prepared.session_key)
        progress = self.sessions.maintenance_progress(session)
        key = window_key(prepared.view)
        removed = set(prepared.removed_message_ids)
        pending = [
            summary_source(message)
            for message in session.messages
            if message.get("id") in removed
        ]
        allowed = removed | set(progress.summary_source_ids.get(key, []))
        state = progress.summaries.get(key, "")
        summary: WorkingSummary | None = None
        diagnostics: list[SummaryAttempt] = []
        try:
            while summary is None or pending:
                count, messages = self._next_batch(state, pending)
                summary = await self.request.rewrite(messages, allowed, diagnostics)
                state = summary.content
                pending = pending[count:]
        except Exception as exc:
            raise SummaryGenerationError(str(exc), tuple(diagnostics)) from exc
        return replace(summary, diagnostics=tuple(diagnostics))

    def _request(self, state: str, sources: list[dict[str, Any]]) -> list[dict]:
        return [
            {"role": "system", "content": self.request.prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {"previous_state": state, "messages": sources},
                    ensure_ascii=False,
                ),
            },
        ]

    def _next_batch(
        self, state: str, pending: list[dict[str, Any]]
    ) -> tuple[int, list[dict]]:
        """Pick the longest prefix of ``pending`` whose request fits the budget."""
        messages = self._request(state, pending)
        if self.request.fits(messages):
            return len(pending), messages
        # Request size grows with the prefix, so binary search the largest fit.
        low, high = 0, len(pending) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self.request.fits(self._request(state, pending[:middle])):
                low = middle
            else:
                high = middle - 1
        if low:
            return low, self._request(state, pending[:low])
        if not pending:
            raise ValueError("工作摘要请求超过模型输入预算")
        # A single message alone exceeds the batch: tighten truncation until it fits.
        limit = _TOOL_RESULT_CHAR_BUDGET
        while limit >= _MIN_TEXT_CHARS:
            messages = self._request(state, [shrink_summary_source(pending[0], limit)])
            if self.request.fits(messages):
                return 1, messages
            limit //= 2
        raise ValueError("工作摘要请求超过模型输入预算")
