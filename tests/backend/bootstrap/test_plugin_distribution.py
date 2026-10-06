"""Only exact bundled package resources are excluded from builtin discovery."""

from bootstrap import plugin_distribution


def test_catalog_distinguishes_shipped_paths_from_same_named_workspace_packages(
    tmp_path, monkeypatch
):
    shipped = tmp_path / "distribution" / "plugins"
    source = shipped / "tencent_asr"
    source.mkdir(parents=True)
    user = tmp_path / "workspace" / "plugins" / "tencent_asr"
    user.mkdir(parents=True)
    monkeypatch.setattr(plugin_distribution, "plugin_roots", lambda: [shipped])
    assert plugin_distribution.bundled_plugin_sources() == {"tencent_asr": source}
    assert plugin_distribution.is_bundled_plugin_source(source)
    assert not plugin_distribution.is_bundled_plugin_source(user)
    assert not plugin_distribution.is_bundled_plugin_source(shipped / "default_memory")


def test_host_only_distribution_has_no_required_voice_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_distribution, "plugin_roots", lambda: [tmp_path])
    assert plugin_distribution.bundled_plugin_sources() == {}
