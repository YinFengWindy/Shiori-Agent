"""Strict SemVer and the supported runtime compatibility comparator grammar."""

import pytest

from agent.plugin_host.versions import SemVer, satisfies


@pytest.mark.parametrize(
    "value", ["1", "1.2", "01.2.3", "1.2.3-01", "v1.2.3", "1.2.3.4"]
)
def test_rejects_non_semver(value):
    with pytest.raises(ValueError):
        SemVer.parse(value)


@pytest.mark.parametrize(
    "version, expression, expected",
    [
        ("2.0.0", ">=2.0.0 <3.0.0", True),
        ("3.0.0", ">=2.0.0 <3.0.0", False),
        ("2.0.0+build.42", "2.0.0", True),
        ("2.1.0-rc.2", ">=2.0.0 <3.0.0", False),
        ("2.1.0-rc.2", ">=2.1.0-rc.1 <2.1.0", True),
        ("2.1.0-rc.10", ">2.1.0-rc.2", True),
        ("2.1.0-alpha", ">2.1.0-1", True),
    ],
)
def test_supported_ranges(version, expression, expected):
    assert satisfies(version, expression) is expected


@pytest.mark.parametrize("value", ["", "^2.0.0", "~2.0.0", "2.*", ">=2.0.0 || <1.0.0"])
def test_rejects_unsupported_range_syntax(value):
    with pytest.raises(ValueError):
        satisfies("2.0.0", value)
