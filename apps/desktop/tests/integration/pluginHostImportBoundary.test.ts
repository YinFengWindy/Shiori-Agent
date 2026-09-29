import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, posix, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { ESLint } from "eslint";

// Exercises the plugin/host import boundary in the repository-root `eslint.config.js` (#503).
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const eslint = new ESLint({ cwd: repoRoot });

/** Lints `code` as if it lived at the repository-relative `path`; returns the boundary violations. */
async function boundaryViolations(code: string, path: string) {
  const [result] = await eslint.lintText(code, { filePath: resolve(repoRoot, path) });
  return result.messages.filter((message) => message.ruleId === "no-restricted-imports");
}

test("plugin renderer and SDK code cannot import host source", async () => {
  const hostImports = [
    'import { cx } from "../../../apps/desktop/renderer/src/shared/styles";',
    'import type { BridgeEvent } from "../../../apps/desktop/src/bridge/shared";',
    'export { deferred } from "../../../../apps/desktop/renderer/src/shared/testing/deferred";',
  ];
  for (const path of ["plugins/boundary_probe/ui/probe.tsx", "plugins/boundary_probe/background/probe.ts", "plugins/boundary_probe/surface/nested/probe.ts", "packages/plugin-sdk/src/probe.ts"]) {
    for (const code of hostImports) assert.equal((await boundaryViolations(code, path)).length, 1, `${path}: ${code}`);
    assert.deepEqual(await boundaryViolations('import { PluginBridgeError } from "@shiori/plugin-sdk";\nimport { deferred } from "@shiori/plugin-sdk/testing";', path), []);
  }
});

test("every exemption names a file that still imports host source", async () => {
  const config = await import(pathToFileURL(resolve(repoRoot, "eslint.config.js")).href);
  const exemptions: unknown = config.pluginHostImportExemptions;
  assert.ok(Array.isArray(exemptions) && exemptions.length > 0);
  for (const path of exemptions) {
    assert.equal(typeof path, "string");
    // A sibling path keeps every relative import meaning the same but is not exempt.
    const probe = posix.join(posix.dirname(path), `__boundary_probe__${posix.extname(path)}`);
    const violations = await boundaryViolations(await readFile(resolve(repoRoot, path), "utf8"), probe);
    assert.ok(violations.length > 0, `${path} no longer imports host source; remove it from pluginHostImportExemptions`);
  }
});
