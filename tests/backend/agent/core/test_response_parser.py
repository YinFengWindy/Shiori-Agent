from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


def _load_response_parser_module():
    repository_root = Path(__file__).resolve().parents[4]
    module_path = (
        repository_root / "apps" / "backend" / "agent" / "core" / "response_parser.py"
    )
    spec = spec_from_file_location("test_response_parser_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec from {module_path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


response_parser = _load_response_parser_module()


def test_parse_response_extracts_structured_mood_from_json_payload() -> None:
    result = response_parser.parse_response(
        '{"content":"她轻轻笑了一下。","mood":"开心"}',
        tool_chain=[],
    )

    assert result.clean_text == "她轻轻笑了一下。"
    assert result.metadata.mood == "开心"


def test_parse_response_keeps_raw_text_when_not_structured_json() -> None:
    result = response_parser.parse_response(
        "她只是安静地看着你。",
        tool_chain=[],
    )

    assert result.clean_text == "她只是安静地看着你。"
    assert result.metadata.mood is None


def test_extract_structured_mood_tolerates_missing_content() -> None:
    clean_text, mood = response_parser.extract_structured_mood('{"mood":"警觉"}')

    assert clean_text == '{"mood":"警觉"}'
    assert mood == "警觉"


def test_parse_response_json_payload_logs_raw_text_on_malformed_json(caplog) -> None:
    """Issue #304: a reply shaped like a JSON object (braces at both ends)
    that fails to parse is a genuine format failure - unlike plain dialogue
    with no braces at all, which is the expected common case post-#303 and
    stays silent. The malformed case must log the raw text so a failed
    round is still diagnosable."""
    malformed = '{"content": "缺了收尾引号}'
    with caplog.at_level("WARNING"):
        result = response_parser.parse_response_json_payload(malformed)

    assert result is None
    messages = [record.getMessage() for record in caplog.records]
    assert any(malformed in message for message in messages)


def test_parse_response_json_payload_log_redacts_leaked_credentials(caplog) -> None:
    """The raw text logged on a malformed-JSON failure must not leak
    credential-shaped substrings the model might echo back - same
    requirement as the other two logging call sites (agent.provider's
    tool-call parsing, agent.core.reply_completion.fetch_role_mood), all
    routed through the shared `core.common.llm_output_log` helper."""
    leaked_key = "sk-" + "c" * 40
    malformed = (
        f'{{"content": "{leaked_key}'  # unterminated string, no closing brace pair
    )
    malformed = malformed + "}"
    with caplog.at_level("WARNING"):
        result = response_parser.parse_response_json_payload(malformed)

    assert result is None
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert leaked_key not in logged
    assert "REDACTED" in logged


def test_parse_response_stays_silent_for_plain_text_without_braces(caplog) -> None:
    """The common post-#303 case - plain dialogue, no JSON envelope at all -
    must not log anything; only a genuine brace-wrapped parse failure does."""
    with caplog.at_level("WARNING"):
        result = response_parser.parse_response(
            "她只是安静地看着你，没有说话。",
            tool_chain=[],
        )

    assert result.clean_text == "她只是安静地看着你，没有说话。"
    assert caplog.records == []


def test_parse_response_extracts_structured_mood_from_embedded_json_payload() -> None:
    result = response_parser.parse_response(
        '前置说明 {"content":"她轻轻偏过头。","mood":"鄙视"} 后置说明',
        tool_chain=[],
    )

    assert result.clean_text == "她轻轻偏过头。"
    assert result.metadata.mood == "鄙视"
