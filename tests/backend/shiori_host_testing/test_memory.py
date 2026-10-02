"""The host integration fake preserves its real workspace-backed memory behavior."""

from pathlib import Path

from agent.memory import MemoryStore
from shiori_host_testing.memory import FakeMemoryEngine


def test_workspace_backed_fake_writes_the_real_host_store(tmp_path: Path) -> None:
    engine = FakeMemoryEngine(tmp_path)
    engine.write_long_term("remember the workspace")
    assert MemoryStore(tmp_path).read_long_term() == "remember the workspace\n"
    assert engine.has_long_term_memory()


def test_unbacked_fake_does_not_create_persistence() -> None:
    engine = FakeMemoryEngine()
    engine.write_long_term("discarded")
    assert engine.read_long_term() == ""
    assert not engine.has_long_term_memory()
