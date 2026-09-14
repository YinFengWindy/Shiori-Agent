"""Entry artifact format checks independent of package schema parsing."""

import pytest

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_artifacts import validate_artifact


@pytest.mark.parametrize(
    "source",
    [
        "async def setup(): pass",
        "async def setup(ctx, other): pass",
        "async def setup(ctx, *, other): pass",
        "def setup(ctx): pass",
        "async def setup(ctx) broken",
    ],
)
def test_rejects_unusable_backend_entry(tmp_path, source):
    (tmp_path / "plugin.py").write_text(source, encoding="utf-8")
    with pytest.raises(PackageContractError) as caught:
        validate_artifact(tmp_path, "plugin.py", "entry", ".py")
    assert caught.value.diagnostic.field == "entry"


@pytest.mark.parametrize(
    "source",
    [
        "",
        "module.exports = {};",
        "// export default {}",
        "const text = 'export default';",
        "export default require('react');",
    ],
)
def test_rejects_non_esm_or_commonjs_entry(tmp_path, source):
    (tmp_path / "ui.mjs").write_text(source, encoding="utf-8")
    with pytest.raises(PackageContractError) as caught:
        validate_artifact(tmp_path, "ui.mjs", "renderer.ui.entry", ".mjs")
    assert caught.value.diagnostic.code == "unsupported_format"


@pytest.mark.parametrize("name", ["ui.js", "ui.cjs", "ui.ts", "ui.tsx", "ui.jsx"])
def test_rejects_source_or_ambiguous_renderer_extension(tmp_path, name):
    (tmp_path / name).write_text("export default {};", encoding="utf-8")
    with pytest.raises(PackageContractError) as caught:
        validate_artifact(tmp_path, name, "renderer.ui.entry", ".mjs")
    assert caught.value.diagnostic.code == "unsupported_format"


def test_esm_allows_comments_and_text_mentioning_commonjs(tmp_path):
    (tmp_path / "ui.mjs").write_text(
        "// module.exports\nexport default {text: 'require(x)'};", encoding="utf-8"
    )
    assert (
        validate_artifact(tmp_path, "ui.mjs", "renderer.ui.entry", ".mjs") == "ui.mjs"
    )


def test_accepts_bundled_default_export(tmp_path):
    (tmp_path / "ui.mjs").write_text(
        "const ui = {};\nexport { ui as default };", encoding="utf-8"
    )
    assert (
        validate_artifact(tmp_path, "ui.mjs", "renderer.ui.entry", ".mjs") == "ui.mjs"
    )


@pytest.mark.parametrize(
    "source",
    [
        'const text = "export { ui as default }";',
        "const text = 'export { ui as default }';",
        "const text = `export { ui as default }`;",
        "// export { ui as default }",
        "/* export { ui as default } */",
        'export { "ui as default" };',
    ],
)
def test_export_text_in_literals_or_comments_is_not_a_default_export(tmp_path, source):
    (tmp_path / "ui.mjs").write_text(source, encoding="utf-8")
    with pytest.raises(PackageContractError) as caught:
        validate_artifact(tmp_path, "ui.mjs", "renderer.ui.entry", ".mjs")
    assert caught.value.diagnostic.code == "unsupported_format"
