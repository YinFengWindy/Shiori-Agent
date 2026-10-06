import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { collectSdkRuntimeModules } from "./runtime-plugin-modules.mjs";
import { assertRuntimeHiddenImports, createRuntimePyinstallerArgs } from "./runtime-pyinstaller.mjs";

test("the real host argument builder retains the complete SDK without installing external providers", async () => {
  const sdkModules = await collectSdkRuntimeModules(fileURLToPath(new URL("../../../packages/sdk/python/shiori_sdk", import.meta.url)));
  const args = createRuntimePyinstallerArgs({
    runtimeRoot: "runtime", workRoot: "work", backendRoot: "backend", stagingRoot: "staging", stagedPluginsDir: "staging/plugins",
    browserRuntime: "browser", computerRuntime: "computer", repositoryRoot: "repository", pluginModules: [], hostModules: ["agent.core"], sdkModules,
  });
  const hidden = args.filter((_value, index) => args[index - 1] === "--hidden-import");
  const paths = args.filter((_value, index) => args[index - 1] === "--paths");
  assert.ok(paths.includes(join("repository", "packages/sdk/python")), "freeze analysis must resolve the same SDK source tree collected on disk");
  for (const name of ["shiori_sdk.files.audio", "shiori_sdk.files.staging", "shiori_sdk.local_http", ...sdkModules]) assert.ok(hidden.includes(name), name);
  assert.equal(hidden.some((name) => name.startsWith("plugins.") || name.startsWith("shiori_sdk.testing")), false);
  assert.ok(args.some((value, index) => value === "shiori_sdk.testing" && args[index - 1] === "--exclude-module"));
});

test("completeness guard examines final flags rather than unrelated argument strings", () => {
  assert.throws(() => assertRuntimeHiddenImports(["--name", "shiori_sdk.files.audio"], ["shiori_sdk.files.audio"]), /hidden imports missing: shiori_sdk.files.audio/);
  assert.doesNotThrow(() => assertRuntimeHiddenImports(["--hidden-import", "shiori_sdk.files.audio"], ["shiori_sdk.files.audio"]));
});
