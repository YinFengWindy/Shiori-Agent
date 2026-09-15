"""External namespace imports use verified source bytes, never discarded caches."""

import importlib
import importlib.util
import os
import py_compile
import sys
import types
from importlib.abc import MetaPathFinder
from importlib.machinery import EXTENSION_SUFFIXES

import pytest

from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trusted_imports import TrustedPluginImports


def test_existing_bytecode_and_changed_lazy_sources_cannot_replace_verified_code(
    tmp_path,
):
    entry = tmp_path / "plugin.py"
    trusted_source = (
        "answer = 42\ndef lazy():\n    from . import helper\n    return helper.answer\n"
    )
    entry.write_text(trusted_source.replace("42", "99"), encoding="utf-8")
    py_compile.compile(str(entry), doraise=True)
    original_stat = entry.stat()
    entry.write_text(trusted_source, encoding="utf-8")
    os.utime(entry, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    helper = tmp_path / "helper.py"
    helper.write_text("answer = 1\n", encoding="utf-8")
    content = inspect_package_content(tmp_path)
    namespace = "akasic_plugin_source_test"
    finder = TrustedPluginImports(namespace, content.sources)
    finder.install()
    try:
        spec = importlib.util.spec_from_file_location(
            namespace,
            entry,
            loader=finder.loader(namespace, entry),
            submodule_search_locations=[str(tmp_path)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[namespace] = module
        spec.loader.exec_module(module)
        assert module.answer == 42
        helper.write_text("answer = 2\n", encoding="utf-8")
        assert module.lazy() == 1
        (tmp_path / "new.py").write_text("answer = 3\n", encoding="utf-8")
        with pytest.raises(ImportError, match="信任"):
            importlib.import_module(namespace + ".new")
        bytecode = tmp_path / "cache_only.py"
        bytecode.write_text("answer = 4\n", encoding="utf-8")
        py_compile.compile(
            str(bytecode), cfile=str(tmp_path / "cache_only.pyc"), doraise=True
        )
        bytecode.unlink()
        with pytest.raises(ImportError, match="信任"):
            importlib.import_module(namespace + ".cache_only")
        (tmp_path / ("native_only" + EXTENSION_SUFFIXES[0])).write_bytes(
            b"not an approved native module"
        )
        with pytest.raises(ImportError, match="信任"):
            importlib.import_module(namespace + ".native_only")
    finally:
        finder.remove()
        for name in list(sys.modules):
            if name == namespace or name.startswith(namespace + "."):
                sys.modules.pop(name)
    assert finder not in sys.meta_path


def test_unknown_plugin_module_never_reaches_a_later_finder(tmp_path):
    reached = []

    class LaterFinder(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            reached.append(fullname)

    finder = TrustedPluginImports("akasic_plugin_closed", {})
    later = LaterFinder()
    package = types.ModuleType("akasic_plugin_closed")
    package.__path__ = [str(tmp_path)]
    sys.modules[package.__name__] = package
    finder.install()
    sys.meta_path.append(later)
    try:
        with pytest.raises(ModuleNotFoundError, match="信任"):
            importlib.import_module("akasic_plugin_closed.missing")
        assert reached == []
    finally:
        finder.remove()
        sys.meta_path.remove(later)
        sys.modules.pop(package.__name__, None)
