from plugins.default_memory.backend.engine.prompts import _default_memory_tool_profile


def test_recall_profile_describes_evidence_fetching():
    spec = _default_memory_tool_profile().recall
    assert spec is not None
    assert "fetch_messages" in spec.description
