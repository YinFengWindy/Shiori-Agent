"""Fixtures loaded only when the SDK testing extra dependencies are available."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
import yaml

from .context import FakePluginContext
from .ssl_context import share_httpx_ssl_contexts


@pytest.fixture(scope="session", autouse=True)
def shared_httpx_ssl_contexts() -> Iterator[None]:
    """Reuses test-session TLS contexts without importing host state."""
    with share_httpx_ssl_contexts():
        yield


def find_plugin_dir(test_path: Path, root: Path) -> Path:
    """Returns the nearest directory from a test file up to ``root`` owning a manifest.

    Plugin tests live inside their package (``<plugin>/tests/``), so the manifest
    sits in an ancestor whether the suite runs in a checkout or a staged copy.
    """
    root = root.resolve()
    for directory in test_path.resolve().parents:
        if (directory / "manifest.yaml").is_file():
            return directory
        if directory == root:
            break
    raise LookupError(
        f"{test_path} 到 {root} 之间没有 manifest.yaml；"
        "请覆盖 sdk_plugin_dir fixture 指向插件包目录"
    )


def read_plugin_id(plugin_dir: Path) -> str:
    """The manifest's plugin id; a manifest that is not a mapping or has no id fails."""
    manifest = plugin_dir / "manifest.yaml"
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"manifest.yaml 格式错误，期望 dict: {manifest}")
    values = cast(dict[str, object], raw)
    plugin_id = values.get("id")
    if not isinstance(plugin_id, str) or not plugin_id:
        raise ValueError(f"manifest 缺少 id: {manifest}")
    return plugin_id


@pytest.fixture
def sdk_plugin_dir(request: pytest.FixtureRequest) -> Path:
    """The plugin package under test; override when tests live outside it."""
    return find_plugin_dir(request.path, request.config.rootpath)


@pytest_asyncio.fixture
async def sdk_context(
    sdk_plugin_dir: Path, tmp_path: Path
) -> AsyncIterator[FakePluginContext]:
    """Declares only the manifest's ``inject`` / ``optional_inject`` / ``provides``.

    Always runs cleanup.

    The manifest is only read; ``plugin_dir`` is an isolated temporary directory so
    tests never write into the plugin package (bundled files are package assets).
    """
    context = FakePluginContext(
        read_plugin_id(sdk_plugin_dir), tmp_path, package_dir=sdk_plugin_dir
    )
    try:
        yield context
    finally:
        await context.aclose()
