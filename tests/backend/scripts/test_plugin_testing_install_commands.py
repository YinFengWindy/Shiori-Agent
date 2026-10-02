"""Static guard: every plugin TESTING.md install command refreshes its wheelhouse packages.

uv caches ``--find-links`` wheels by name and version, so a rebuilt wheelhouse
package installs the stale cached build unless the command names it with
``--refresh-package``. The expected set comes from the same dependency closure
``scripts.verify_plugin_tests`` installs, so adding a sibling dependency without
updating the plugin's TESTING.md fails here.
"""

import shlex

import pytest

from scripts import verify_plugin_tests as runner
from scripts.sdk_boundaries import plugin_distribution

PLUGINS = sorted(
    path.parent.name for path in runner.REPOSITORY.glob("plugins/*/TESTING.md")
)


def _install_command(plugin_id: str) -> list[str]:
    testing = runner.REPOSITORY / "plugins" / plugin_id / "TESTING.md"
    (line,) = (
        line
        for line in testing.read_text(encoding="utf-8").splitlines()
        if line.startswith("uv pip install ") and "--find-links" in line
    )
    return shlex.split(line)


@pytest.mark.parametrize("plugin_id", PLUGINS)
def test_manual_install_refreshes_every_wheelhouse_package(plugin_id: str) -> None:
    command = _install_command(plugin_id)
    refreshed = {
        command[index + 1]
        for index, token in enumerate(command)
        if token == "--refresh-package"
    }
    # The command installs the target's runtime and test closure.
    siblings = runner.plugin_dependencies({plugin_id}, extras=frozenset({"test"}))
    expected = {"shiori-sdk", *map(plugin_distribution, siblings - {plugin_id})}
    # A source install (".[test]") rebuilds the copy; a by-name install takes the
    # target itself from the wheelhouse, so it needs a refresh too.
    if not command[-1].startswith("."):
        expected.add(plugin_distribution(plugin_id))
    assert refreshed == expected


def test_every_plugin_with_tests_documents_a_manual_install() -> None:
    tested = {
        path.name
        for path in (runner.REPOSITORY / "plugins").iterdir()
        if any((path / "tests").rglob("test_*.py"))
    }
    assert tested <= set(PLUGINS)
