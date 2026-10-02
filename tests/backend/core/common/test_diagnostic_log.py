from core.common.diagnostic_log import diagnostic_line


def test_diagnostic_line_uses_fixed_field_order():
    line = diagnostic_line(
        "PassiveTurnPipeline.run",
        event="start",
        flow="passive",
        phase="before_turn",
        session="telegram:1",
        turn="abc123",
        action="run",
    )
    assert line == (
        "[PassiveTurnPipeline.run] event=start flow=passive phase=before_turn "
        "session=telegram:1 turn=abc123 tick=- action=run reason=- "
        'duration_ms=- counts=- error_type=- error_fp=- note="-"'
    )
