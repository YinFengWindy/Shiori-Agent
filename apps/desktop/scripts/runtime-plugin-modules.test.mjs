import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { collectHostBackendModules, collectPluginBackendModules } from "./runtime-plugin-modules.mjs";

test("collectPluginBackendModules discovers namespace backends and nested packages", async () => {
  const directory = await mkdtemp(join(tmpdir(), "shiori-runtime-modules-"));
  try {
    for (const relativePath of [
      "akasha/backend/memory_plugin.py",
      "akasha/backend/core.py",
      "akasha/backend/fast/graph_fast.py",
      "default_memory/backend/engine/__init__.py",
      "default_memory/backend/engine/lifecycle.py",
      "default_memory/backend/memory_plugin.py",
      "default_memory/backend/config.local.toml",
      "akasha/tests/test_plugin.py",
      "akasha/ui/preview.py",
      "akasha/backend/__pycache__/cache.py",
      "skin/manifest.yaml",
    ]) {
      const path = join(directory, relativePath);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, "", "utf8");
    }

    assert.deepEqual(await collectPluginBackendModules(directory), [
      "plugins.akasha.backend.core",
      "plugins.akasha.backend.fast.graph_fast",
      "plugins.akasha.backend.memory_plugin",
      "plugins.default_memory.backend.engine",
      "plugins.default_memory.backend.engine.lifecycle",
      "plugins.default_memory.backend.memory_plugin",
    ]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("collectHostBackendModules enumerates implicit namespace subdirectories without __init__.py", async () => {
  // 复刻真实的坑：agent/tools/ 没有 __init__.py。CPython 的
  // pkgutil.iter_modules（PyInstaller --collect-submodules 依赖它）会直接跳过
  // 这种目录，历史上导致 agent.tools.* 整体漏收（#315）。这里如果退回旧的
  // --collect-submodules 语义，下面的断言会失败。
  const directory = await mkdtemp(join(tmpdir(), "shiori-runtime-host-modules-"));
  try {
    for (const relativePath of [
      "agent/__init__.py",
      "agent/core.py",
      "agent/tools/base.py",
      "agent/tools/registry.py",
      "agent/tools/shell/runner.py",
      "agent/tools/meta/__init__.py",
      "agent/tools/meta/handler.py",
      "agent/__pycache__/cache.py",
      "bootstrap/__init__.py",
      "bootstrap/app.py",
    ]) {
      const path = join(directory, relativePath);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, "", "utf8");
    }

    const modules = await collectHostBackendModules(directory, ["agent", "bootstrap"]);

    assert.deepEqual(modules, [
      "agent",
      "agent.core",
      "agent.tools.base",
      "agent.tools.meta",
      "agent.tools.meta.handler",
      "agent.tools.registry",
      "agent.tools.shell.runner",
      "bootstrap",
      "bootstrap.app",
    ]);

    // 显式核对本次修复要保证的三类场景都命中了。
    assert.ok(modules.includes("agent.tools.base"), "没有 __init__.py 的命名空间目录必须被枚举");
    assert.ok(modules.includes("agent.tools.shell.runner"), "嵌套命名空间目录必须被枚举");
    assert.ok(
      modules.includes("agent.tools.meta") && modules.includes("agent.tools.meta.handler"),
      "带 __init__.py 的包必须同时产出包名与其子模块",
    );
    assert.ok(
      !modules.some((name) => name.includes("__pycache__") || name.includes("cache")),
      "__pycache__ 必须被排除",
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
