import assert from "node:assert/strict";
import { access, mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { stageBuiltinPlugins } from "./runtime-plugin-staging.mjs";
import { collectPluginBackendModules } from "./runtime-plugin-modules.mjs";

test("frozen staging excludes external source before hidden-import collection", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "runtime-plugin-staging-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = join(root, "source"), staged = join(root, "staged");
  for (const id of ["bundled", "separate"]) {
    for (const file of ["backend/plugin.py", "tests/test_plugin.py", "backend/__pycache__/cached.py"]) {
      const parts = file.split("/");
      await mkdir(join(source, id, ...parts.slice(0, -1)), { recursive: true });
      await writeFile(join(source, id, ...parts), "# test\n", "utf8");
    }
    await writeFile(join(source, id, "manifest.yaml"), `api: 2\nid: ${id}\n${id === "separate" ? "distribution: external\n" : ""}`, "utf8");
  }
  await stageBuiltinPlugins(source, staged);
  assert.deepEqual(await collectPluginBackendModules(staged), ["plugins.bundled.backend.plugin"]);
  for (const excluded of ["separate", "bundled/tests", "bundled/backend/__pycache__"]) await assert.rejects(access(join(staged, excluded)));
});
