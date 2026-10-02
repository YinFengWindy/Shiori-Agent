"""Offline installation resolves every shiori package from local wheel files only."""

from pathlib import Path
import zipfile

import pytest

from scripts import wheelhouse as installer


def _wheel(wheelhouse: Path, name: str, version: str, *requires: str) -> Path:
    wheel = wheelhouse / f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"{name.replace('-', '_')}-{version}.dist-info/METADATA",
            f"Name: {name}\nVersion: {version}\n"
            + "".join(f"Requires-Dist: {requirement}\n" for requirement in requires),
        )
    return wheel


def test_shiori_packages_install_offline_from_wheelhouse_files_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    sdk = _wheel(
        wheelhouse,
        "shiori-sdk",
        "3.0.0",
        "httpx>=0.28",
        "pytest-asyncio>=1; extra == 'testing'",
    )
    meme = _wheel(
        wheelhouse,
        "shiori-plugin-meme",
        "0.1.0",
        "shiori-sdk==3.0.0",
        "shiori-plugin-citation==0.1.0",
        "shiori-sdk[testing]==3.0.0; extra == 'test'",
    )
    citation = _wheel(wheelhouse, "shiori-plugin-citation", "0.1.0")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        installer, "run", lambda command, **kwargs: commands.append(command) or ""
    )
    installer.install_from_wheelhouse(
        tmp_path / "python",
        wheelhouse,
        ["shiori-plugin-meme[test]"],
        cwd=tmp_path,
        log=tmp_path / "install.log",
    )
    local, remote, check = commands
    assert {"--no-index", "--no-deps"} <= set(local)
    assert "--find-links" not in local
    assert set(local[-3:]) == {str(sdk), str(meme), str(citation)}
    assert remote[-2:] == ["httpx>=0.28", "pytest-asyncio>=1"]
    assert check[1:3] == ["pip", "check"]


@pytest.mark.parametrize(
    "local,third_party",
    [
        # A shiori dependency missing from the wheelhouse is never fetched.
        (["shiori-plugin-story"], []),
        (["shiori-sdk"], ["shiori-plugin-novelai"]),
        # A local root missing from the wheelhouse is not treated as remote.
        (["unbuilt-target"], []),
    ],
)
def test_shiori_packages_cannot_fall_back_to_an_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local: list[str],
    third_party: list[str],
) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    _wheel(wheelhouse, "shiori-sdk", "3.0.0")
    _wheel(wheelhouse, "shiori-plugin-story", "0.1.0", "shiori-plugin-novelai")
    monkeypatch.setattr(installer, "run", lambda *args, **kwargs: pytest.fail("ran"))
    with pytest.raises(ValueError, match="wheelhouse"):
        installer.install_from_wheelhouse(
            tmp_path / "python",
            wheelhouse,
            local,
            third_party=third_party,
            cwd=tmp_path,
            log=tmp_path / "install.log",
        )


def test_closure_applies_extras_per_edge_and_markers_per_context() -> None:
    declared = {
        "target": ["sibling", "tool; extra == 'test'", "skipped; extra == 'other'"],
        "sibling": ["base-only", "sibling-extra; extra == 'test'"],
    }
    local, external = installer.requirement_closure(
        ["target[test]"], lambda name, _extra: declared.get(name)
    )
    assert set(local) == {"target", "sibling"}
    # The sibling edge requested no extra, so its test requirements stay inactive.
    assert {(declarer, str(requirement)) for declarer, requirement in external} == {
        ("sibling", "base-only"),
        ("target", 'tool; extra == "test"'),
    }
