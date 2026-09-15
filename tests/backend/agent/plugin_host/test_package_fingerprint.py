"""Whole-package trust identity excludes only non-executable Python cache data."""

import pytest

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_fingerprint import inspect_package_content


def test_content_names_and_real_directory_are_bound_but_bytecode_is_not(
    contract_package,
):
    initial = inspect_package_content(contract_package)
    cache = contract_package / "backend" / "__pycache__"
    cache.mkdir()
    (cache / "plugin.pyc").write_bytes(b"generated")
    assert inspect_package_content(contract_package).fingerprint == initial.fingerprint
    assert not any(path.endswith(".pyc") for path in initial.sources)
    for folder in (cache, contract_package / "assets.pyc"):
        folder.mkdir(exist_ok=True)
        published = folder / "index.mjs"
        published.write_text("export default 1", encoding="utf-8")
        first = inspect_package_content(contract_package).fingerprint
        published.write_text("export default 2", encoding="utf-8")
        assert inspect_package_content(contract_package).fingerprint != first
        published.unlink()
    for relative in (
        "manifest.yaml",
        "backend/plugin.py",
        "renderer/ui.mjs",
        "renderer/style.css",
    ):
        path = contract_package / relative
        original = path.read_bytes()
        path.write_bytes(original + b"\n# changed")
        assert (
            inspect_package_content(contract_package).fingerprint != initial.fingerprint
        )
        path.write_bytes(original)
    asset = contract_package / "new-asset.txt"
    asset.write_text("new", encoding="utf-8")
    assert inspect_package_content(contract_package).fingerprint != initial.fingerprint
    asset.unlink()
    moved = contract_package.with_name("moved")
    contract_package.rename(moved)
    assert inspect_package_content(moved).fingerprint != initial.fingerprint


def test_package_links_cannot_extend_the_approved_contents(contract_package, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("unsafe", encoding="utf-8")
    try:
        (contract_package / "linked.py").symlink_to(outside)
    except OSError:
        pytest.skip("File symlinks are unavailable on this Windows installation")
    with pytest.raises(PackageContractError, match="链接"):
        inspect_package_content(contract_package)
