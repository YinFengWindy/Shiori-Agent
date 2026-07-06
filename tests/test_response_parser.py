from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


def _load_response_parser_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "agent" / "core" / "response_parser.py"
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


def test_parse_response_extracts_structured_mood_from_embedded_json_payload() -> None:
    result = response_parser.parse_response(
        '前置说明 {"content":"她轻轻偏过头。","mood":"鄙视"} 后置说明',
        tool_chain=[],
    )

    assert result.clean_text == "她轻轻偏过头。"
    assert result.metadata.mood == "鄙视"
