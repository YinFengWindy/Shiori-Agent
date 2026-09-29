from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.identity.pairing import PAIRING_CODE_TTL, PairingCodes

START = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def test_a_code_is_consumed_once() -> None:
    codes = PairingCodes(_Clock())
    code = codes.create()

    assert codes.consume(f"  {code.code.lower()}\n")
    assert not codes.consume(code.code)


def test_a_wrong_code_does_not_use_up_the_pending_one() -> None:
    codes = PairingCodes(_Clock())
    code = codes.create()

    assert not codes.consume("你好")
    assert not codes.consume("ABCD2345" if code.code != "ABCD2345" else "ABCD2346")
    assert codes.consume(code.code)


def test_a_code_expires_after_ten_minutes() -> None:
    clock = _Clock()
    codes = PairingCodes(clock)
    code = codes.create()
    assert code.expires_at == START + PAIRING_CODE_TTL == START + timedelta(minutes=10)

    clock.now = code.expires_at
    assert not codes.consume(code.code)


def test_a_new_code_replaces_the_previous_one() -> None:
    codes = PairingCodes(_Clock())
    first = codes.create()
    second = codes.create()

    assert first.code == second.code or not codes.consume(first.code)
    assert codes.consume(second.code)
