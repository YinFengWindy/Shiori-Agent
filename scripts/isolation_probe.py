"""Stdlib-only provenance probe copied into each repository-external environment."""

import hashlib
import importlib.util
import json
import sys
import sysconfig
import zipfile
from importlib.metadata import Distribution, distributions, version
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname


def content_mismatch(dist: Distribution, wheel: Path) -> list[str]:
    """Installed paths whose content differs from the wheelhouse wheel ``wheel``.

    An installer cache can serve an older build with the same name, version
    and recorded wheel URL, so only the installed bytes prove the wheel file
    was installed. Every wheel member must match; every installed package file
    must come from the wheel. Installer-written dist-info files and bytecode
    are not wheel content.
    """
    with zipfile.ZipFile(wheel) as archive:
        members = {name for name in archive.namelist() if not name.endswith("/")}
        # .data payloads are relocated on install and are not expected here.
        assert not any(
            name.split("/", 1)[0].endswith(".data") for name in members
        ), f"Unsupported .data payload in {wheel.name}"
        stale = [
            name
            for name in sorted(members)
            if not name.endswith(".dist-info/RECORD")
            and (
                not (path := Path(str(dist.locate_file(name)))).is_file()
                or path.read_bytes() != archive.read(name)
            )
        ]
    assert dist.files is not None, f"No RECORD for {wheel.name}"
    for file in dist.files:
        parts = file.parts
        if (
            parts[0] != ".."
            and not parts[0].endswith(".dist-info")
            and "__pycache__" not in parts
            and str(file) not in members
        ):
            stale.append(str(file))
    return stale


def audit() -> dict[str, object]:
    """Fail if imports, installations, or executed modules escape the private environment.

    The probe runs stdlib-only outside the checkout, so distribution naming
    rules come from ``isolation.json`` (written from ``scripts.sdk_boundaries``).
    """
    config = json.loads(Path("isolation.json").read_text(encoding="utf-8"))
    repository = Path(config["repository"]).resolve()
    wheelhouse = Path(config["wheelhouse"]).resolve()
    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    for entry in sys.path:
        assert not Path(entry).resolve().is_relative_to(repository), entry
    for name in config["host_roots"]:
        assert name not in sys.modules, f"Host module loaded: {name}"
        assert importlib.util.find_spec(name) is None, f"Host import available: {name}"
    installed = {}
    for dist in distributions():
        name = dist.metadata["Name"].lower().replace("_", "-")
        assert Path(str(dist.locate_file(""))).resolve().is_relative_to(site), name
        direct = dist.read_text("direct_url.json")
        assert not direct or not json.loads(direct).get("dir_info", {}).get(
            "editable"
        ), f"Editable installation: {name}"
        if name.startswith(config["local_prefix"]):
            # Index installs record no direct_url.json; a wheel file does.
            origin = json.loads(direct or "{}").get("url", "")
            assert origin.startswith(
                "file:"
            ), f"Not installed from a local wheel: {name}"
            wheel = Path(url2pathname(urlparse(origin).path)).resolve()
            assert wheel.is_relative_to(wheelhouse), (name, str(wheel))
            stale = content_mismatch(dist, wheel)
            assert (
                not stale
            ), f"Installed {name} differs from wheelhouse wheel {wheel.name}: {stale}"
        installed[name] = dist.version
    assert not set(config["host_distributions"]) & installed.keys()
    allowed = set(config["allowed_plugins"])
    plugins = {name for name in installed if name.startswith(config["plugin_prefix"])}
    assert plugins == allowed
    paths = {}
    for name, module in tuple(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if origin and not origin.startswith("<"):
            assert not Path(origin).resolve().is_relative_to(repository), (name, origin)
    for name in ("shiori_sdk", "shiori_sdk.testing", *config["modules"]):
        spec = importlib.util.find_spec(name)
        assert spec is not None and spec.origin is not None, name
        path = Path(spec.origin).resolve()
        assert path.is_relative_to(site), (name, path)
        paths[name] = str(path)
        if name in config["modules"]:
            source = Path(config["modules"][name])
            assert (
                hashlib.sha256(path.read_bytes()).digest()
                == hashlib.sha256(source.read_bytes()).digest()
            ), name
    assert version("shiori-sdk") == config["sdk_version"]
    import shiori_sdk

    assert (
        shiori_sdk.__version__
        == shiori_sdk.RUNTIME_API_VERSION
        == config["sdk_version"]
    )
    result = {
        "modules": paths,
        "distributions": installed,
        "allowed_plugins": sorted(allowed),
        "absent_host_roots": config["host_roots"],
        "sys_path": sys.path,
        "sdk_version": version("shiori-sdk"),
        "repository_path_injection": False,
        "editable": False,
        "source_packages": config["source_packages"],
        "wheelhouse": str(wheelhouse),
    }
    Path("provenance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def pytest_load_initial_conftests(early_config, parser, args) -> None:
    """Guard executed source before even the external test conftests are imported."""
    config = json.loads(Path("isolation.json").read_text(encoding="utf-8"))
    repository = Path(config["repository"]).resolve()
    sources = [Path(source).resolve() for source in config["source_packages"]]

    def check_execution(event: str, arguments: tuple[object, ...]) -> None:
        if event != "exec":
            return
        filename = getattr(arguments[0], "co_filename", "")
        if not filename or filename.startswith("<"):
            return
        path = Path(filename).resolve()
        assert not path.is_relative_to(repository), (
            "Repository implementation executed instead of installed wheel",
            path,
        )
        for source in sources:
            if path.is_relative_to(source):
                relative = path.relative_to(source)
                assert relative.parts[0] == "tests", (
                    "Plugin implementation executed from source copy instead of installed wheel",
                    path,
                )

    # The exec event observes temporary alias modules even if fixtures remove
    # them from sys.modules before sessionfinish. Test files remain external.
    sys.addaudithook(check_execution)


def pytest_sessionstart(session) -> None:
    """Check the environment before collecting or executing plugin tests."""
    audit()


def pytest_sessionfinish(session, exitstatus) -> None:
    """Check again after tests so test-time path/module injections cannot go unnoticed."""
    audit()
