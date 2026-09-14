"""Host dependency inventory reads metadata without loading dependency modules."""

from importlib import metadata

from agent.plugin_host.host_contract import (
    HostRuntimeContract,
    installed_host_dependencies,
)


def test_inventory_excludes_missing_conditional_and_plugin_distributions(monkeypatch):
    monkeypatch.setattr(
        metadata,
        "requires",
        lambda name: [
            "PyYAML>=6",
            "pydantic>=2",
            "not-installed",
            "shiori-plugin-default-memory==0.1.0",
            "pytest; extra == 'dev'",
        ],
    )

    def installed(name):
        if name == "not-installed":
            raise metadata.PackageNotFoundError(name)
        return "1.0.0"

    monkeypatch.setattr(metadata, "version", installed)
    assert installed_host_dependencies() == frozenset({"pyyaml", "pydantic"})


def test_absent_distribution_metadata_is_fail_closed(monkeypatch):
    def missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "requires", missing)
    assert installed_host_dependencies() == frozenset()


def test_distribution_name_normalization():
    host = HostRuntimeContract(python_dependencies=frozenset({"python-telegram-bot"}))
    assert host.provides_python("Python_Telegram.Bot")
    assert not host.provides_python("private-library")
