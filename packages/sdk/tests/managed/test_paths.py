"""Drive/UNC normalization and real deep filesystem cleanup stay inside private roots."""

import os
import shutil
from pathlib import Path

import pytest

from shiori_sdk.managed.paths import (
    environment_path,
    native_path,
    windows_extended_path,
)


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "D:/环境 with spaces/python/python.exe",
            "\\\\?\\D:\\环境 with spaces\\python\\python.exe",
        ),
        (
            "\\\\server\\share\\environment\\python.exe",
            "\\\\?\\UNC\\server\\share\\environment\\python.exe",
        ),
        ("\\\\?\\D:\\environment\\python.exe", "\\\\?\\D:\\environment\\python.exe"),
    ],
)
def test_windows_paths_preserve_drive_unc_and_existing_prefix(source, expected):
    assert windows_extended_path(source) == expected


def test_relative_windows_path_is_not_reinterpreted_as_a_private_absolute_path():
    with pytest.raises(ValueError, match="绝对路径"):
        windows_extended_path("runtime/python.exe")


def test_third_party_environment_values_keep_the_same_private_directory(tmp_path):
    extended = native_path(tmp_path / "runtime/tmp")
    value = environment_path(extended)
    assert not value.startswith("\\\\?\\")
    assert native_path(Path(value)) == extended


@pytest.mark.skipif(os.name != "nt", reason="Windows long-path filesystem boundary")
def test_deep_private_files_can_be_published_and_removed_without_registry_changes(
    tmp_path,
):
    root = native_path(tmp_path)
    staging = root / "staging" / ("nested-environment-" * 5)
    path = staging / ("package-data-" * 8) / "settings.json"
    assert len(str(path)) > 260
    path.parent.mkdir(parents=True)
    path.write_text("独立环境", encoding="utf-8")
    destination = root / "versions" / ("complete-environment-" * 5)
    destination.parent.mkdir()
    staging.rename(destination)
    assert (destination / path.relative_to(staging)).read_text(
        encoding="utf-8"
    ) == "独立环境"
    shutil.rmtree(destination)
    assert not destination.exists()
