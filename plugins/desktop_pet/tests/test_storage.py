"""Asset paths reject traversal out of the plugin data root."""

import pytest
from plugins.desktop_pet.backend.storage import asset_path, role_asset_directory


def test_asset_paths_reject_traversal(tmp_path):
    with pytest.raises(ValueError):
        asset_path(tmp_path, "../outside")
    with pytest.raises(ValueError):
        role_asset_directory(tmp_path, "../mira")
