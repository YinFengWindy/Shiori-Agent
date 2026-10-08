"""Scripted external-turn submissions for plugin tests; no role turn runs."""

from collections.abc import Awaitable, Callable, Iterable

from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurnResult

# A queued answer: the result itself, or a coroutine function producing it
# (e.g. one that waits on an event, to test a turn still in flight).
type FakeExternalTurnAnswer = (
    ExternalTurnResult | Callable[[ExternalTurnMessage], Awaitable[ExternalTurnResult]]
)


class FakeExternalTurns:
    """Records every submission and answers with the queued ``answers`` in order.

    A submission with nothing queued fails the test, so a plugin that submits
    unexpectedly is visible. Messages are validated by the shared
    ``ExternalTurnMessage`` contract; host-side checks (role existence,
    reserved platforms) are not reproduced.
    """

    def __init__(self, answers: Iterable[FakeExternalTurnAnswer] = ()):
        self.answers = list(answers)
        self.submitted: list[ExternalTurnMessage] = []

    async def submit(self, message: ExternalTurnMessage) -> ExternalTurnResult:
        """Record ``message`` and return the next queued answer."""
        self.submitted.append(message)
        if not self.answers:
            raise AssertionError(f"FakeExternalTurns 没有排队的结果: {message}")
        answer = self.answers.pop(0)
        if isinstance(answer, ExternalTurnResult):
            return answer
        return await answer(message)
