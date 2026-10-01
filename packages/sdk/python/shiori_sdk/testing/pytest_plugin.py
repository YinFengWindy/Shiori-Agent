"""Safe pytest auto-loading for both the base SDK and the optional testing extra."""

from importlib.util import find_spec

import pytest


class _MissingTestingExtra:
    @pytest.fixture
    def sdk_context(self) -> None:
        pytest.fail(
            "The sdk_context fixture requires shiori-sdk[testing]; "
            "install that extra to enable pytest-asyncio and httpx support.",
            pytrace=False,
        )


def pytest_configure(config: pytest.Config) -> None:
    """Registers optional fixtures without requiring them for unrelated test suites."""
    if all(find_spec(name) is not None for name in ("pytest_asyncio", "httpx")):
        from . import pytest_fixtures

        config.pluginmanager.register(pytest_fixtures, "shiori_sdk_testing")
    else:
        config.pluginmanager.register(_MissingTestingExtra(), "shiori_sdk_testing")
