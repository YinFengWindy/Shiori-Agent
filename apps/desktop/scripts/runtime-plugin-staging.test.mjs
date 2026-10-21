import assert from "node:assert/strict";
import { access, cp, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { stageBuiltinPlugins } from "./runtime-plugin-staging.mjs";
import { collectPluginBackendModules } from "./runtime-plugin-modules.mjs";

test("the shipped Grok backend and callback client enter the frozen builtin resources", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "grok-builtin-staging-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = join(root, "source"), staged = join(root, "staged");
  const grok = fileURLToPath(new URL("../../../plugins/grok_bot", import.meta.url));
  await cp(grok, join(source, "grok_bot"), { recursive: true });
  await stageBuiltinPlugins(source, staged);

  const modules = await collectPluginBackendModules(staged);
  assert.ok(modules.includes("plugins.grok_bot.backend.plugin"));
  assert.ok(modules.includes("plugins.grok_bot.backend.callback_server"));
  assert.deepEqual(await readFile(join(staged, "grok_bot", "client.ps1")), await readFile(join(grok, "client.ps1")));
  await assert.rejects(access(join(staged, "grok_bot", "tests")));
});

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
