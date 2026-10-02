"""The dependency guard follows actual host packages instead of a frozen list."""

from pathlib import Path

from scripts.sdk_boundaries import host_roots


def test_new_host_package_and_entry_module_join_the_boundary(tmp_path: Path) -> None:
    backend = tmp_path / "apps/backend"
    (backend / "new_service").mkdir(parents=True)
    (backend / "new_service/service.py").touch()
    (backend / "main.py").touch()
    (backend / "requirements").mkdir()
    assert {"new_service", "main", "memory2", "shiori_host_testing"} <= host_roots(
        tmp_path
    )
    assert "requirements" not in host_roots(tmp_path)
