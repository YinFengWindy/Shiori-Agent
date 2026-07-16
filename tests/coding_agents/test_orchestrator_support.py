from __future__ import annotations

from coding_agents.orchestrator_support import safe_environment


def test_safe_environment_excludes_provider_and_shiori_secrets(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "bin")
    monkeypatch.setenv("SYSTEMROOT", "C:/Windows")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("SHIORI_PRIVATE_TOKEN", "shiori-secret")

    environment = safe_environment()

    assert environment["PATH"] == "bin"
    assert environment["SYSTEMROOT"] == "C:/Windows"
    assert "OPENAI_API_KEY" not in environment
    assert "ANTHROPIC_API_KEY" not in environment
    assert "SHIORI_PRIVATE_TOKEN" not in environment
