import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { collectPluginBackendModules } from "./runtime-plugin-modules.mjs";

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
