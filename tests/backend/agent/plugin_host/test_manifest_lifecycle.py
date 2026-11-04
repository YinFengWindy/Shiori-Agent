"""Every repository manifest runs through the real host lifecycle."""

import pytest
from tests.support.plugin_contracts import (
    ROOT,
    manifest_ids,
    profile_for,
    verify_contract,
)


@pytest.mark.parametrize("plugin_id", manifest_ids())
async def test_manifest_lifecycle(plugin_id, tmp_path):
    await verify_contract(
        plugin_id, tmp_path, profile=profile_for(ROOT / "plugins" / plugin_id)
    )
