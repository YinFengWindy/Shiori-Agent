"""Operation tokens and owned paths cannot become arbitrary filesystem targets."""

import pytest

from desktop_bridge.runtime.plugin_package_store import PluginPackageStore, owned_child
from agent.plugin_host.diagnostics import PackageContractError


@pytest.mark.parametrize(
    "name", ["../outside", "C:/outside", "two/directories", "name:stream", "CON"]
)
def test_rejects_path_bearing_directory_names(tmp_path, name):
    with pytest.raises((ValueError, PackageContractError)):
        owned_child(tmp_path, name)


def test_missing_or_path_bearing_operation_tokens_cannot_remove_other_data(tmp_path):
    keep = tmp_path / "important.txt"
    keep.write_text("keep", encoding="utf-8")
    store = PluginPackageStore(tmp_path)
    with pytest.raises(ValueError):
        store.remove("../../important.txt")
    assert keep.read_text(encoding="utf-8") == "keep"


def test_competing_confirmed_operations_reject_a_second_writer(plugin_package_env):
    env = plugin_package_env
    first = env.preview()
    second = env.preview()
    env.packages.confirm({"token": first["token"], "trusted": True})
    with pytest.raises(ValueError, match="待重启"):
        env.packages.store.assert_available("demo", except_token=second["token"])
