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
