"""Canonical path and portable directory traversal validation."""

import pytest

from shiori_sdk.storage import plugin_data_dir


def test_plugin_data_path_is_pure_and_keeps_the_existing_layout(tmp_path):
    workspace = tmp_path / "not-created"
    assert plugin_data_dir(workspace, "demo") == workspace / "plugin-data" / "demo"
    assert not workspace.exists()


@pytest.mark.parametrize(
    "plugin_id",
    ["", ".", "..", "../outside", "folder/child", "folder\\child", "D:outside"],
)
def test_plugin_data_paths_reject_nonportable_directory_traversal(tmp_path, plugin_id):
    with pytest.raises(ValueError, match="ID"):
        plugin_data_dir(tmp_path, plugin_id)
