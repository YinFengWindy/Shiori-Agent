import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { builtinPluginDirectories, readPluginManifest } from "./plugin-distribution.mjs";

test("source classification defaults only when absent and rejects invalid explicit values", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "plugin-distribution-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const [name, field] of [["builtin", ""], ["external", "distribution: external\n"], ["explicit", "distribution: builtin\n"]]) {
    await mkdir(join(root, name));
    await writeFile(join(root, name, "manifest.yaml"), `api: 2\nid: ${name}\n${field}`, "utf8");
  }
  assert.deepEqual(await builtinPluginDirectories(root), [join(root, "builtin"), join(root, "explicit")]);
  for (const value of ["null", "false", "[]", "other"]) {
    await writeFile(join(root, "external/manifest.yaml"), `distribution: ${value}\n`, "utf8");
    await assert.rejects(readPluginManifest(join(root, "external")), /Invalid plugin distribution/);
  }
});
