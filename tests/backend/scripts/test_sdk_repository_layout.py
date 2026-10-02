"""One repository-layout definition for path rules and literal scans."""

from pathlib import Path

import pytest

from scripts.sdk_repository_layout import host_layout, layout_literal


@pytest.mark.parametrize(
    "relative,expected",
    [
        ("apps/desktop/main.ts", True),
        ("tests/backend/conftest.py", True),
        ("bootstrap", True),
        ("bootstrap/missing.yaml", True),
        ("core/enabled", False),
        ("tests/fixtures/x.json", False),
        ("x.yaml", False),
    ],
)
def test_host_layout_matches_the_actual_backend_tree(
    tmp_path: Path, relative: str, expected: bool
) -> None:
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "core").mkdir()
    assert host_layout(relative, tmp_path) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("apps/backend/prompts/system.md", True),
        ("./tests/backend/agent/fixtures.json", True),
        (r"apps\desktop\main.ts", True),
        ("https://github.com/YinFengWindy/Shiori-Agent/tree/main/apps/backend/", False),
        ("Moved from apps/backend/ to the SDK.", False),
        ("plugins/x/tests/backend/data.json", False),
        ("apps/backend", False),
    ],
)
def test_literals_only_count_when_they_start_with_a_repository_directory(
    text: str, expected: bool
) -> None:
    assert layout_literal(text) is expected
