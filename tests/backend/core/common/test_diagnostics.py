"""Host diagnostics resolves package origins without assuming a repository depth."""

from importlib.machinery import ModuleSpec
import pytest
from core.common import diagnostics
from core.common.diagnostics import HostDiagnostics
from core.error_context import current_session_key


@pytest.mark.parametrize("layout", ["checkout/apps/backend", "venv/Lib/site-packages"])
def test_owned_package_roots_cover_source_and_installed_wheel(
    tmp_path, monkeypatch, layout
):
    names = []

    def spec_for(name):
        names.append(name)
        spec = ModuleSpec(name, None, is_package=True)
        spec.submodule_search_locations = [str(tmp_path / layout / name)]
        return spec

    monkeypatch.setattr(diagnostics, "find_spec", spec_for)
    service = HostDiagnostics()
    file = tmp_path / layout / "infra/net/request.py"
    code = compile("raise RuntimeError('failed')", str(file), "exec")
    try:
        exec(code, {})
    except RuntimeError as error:
        assert service.top_frame(error.__traceback__) == "infra/net/request.py:1"
    assert {
        "bootstrap",
        "infra",
        "desktop_bridge",
        "conversation",
        "proactive_v2",
        "prompts",
        "utils",
        "shiori_runtime_resources",
    } <= set(names)


@pytest.mark.parametrize(
    "root", ["external/extensions/custom", "wheel/site-packages/plugins/observe"]
)
def test_external_plugin_attribution_is_registered_explicitly(tmp_path, root):
    directory = tmp_path / root
    service = HostDiagnostics([("plugins/custom", directory)])
    try:
        exec(
            compile(
                "raise RuntimeError('failed')",
                str(directory / "backend/plugin.py"),
                "exec",
            ),
            {},
        )
    except RuntimeError as error:
        assert (
            service.top_frame(error.__traceback__)
            == "plugins/custom/backend/plugin.py:1"
        )
    assert service.top_frame(None) == "?"


def test_session_context_comes_from_the_host_owner():
    token = current_session_key.set("role:mira")
    try:
        assert HostDiagnostics().session_key() == "role:mira"
    finally:
        current_session_key.reset(token)
