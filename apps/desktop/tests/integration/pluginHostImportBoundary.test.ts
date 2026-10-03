import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";

// Exercises the plugin/host import boundary in the repository-root `eslint.config.js` (#503).
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const eslint = new ESLint({ cwd: repoRoot });

/** Lints `code` as if it lived at the repository-relative `path`; returns the boundary violations. */
async function boundaryViolations(code: string, path: string) {
  const [result] = await eslint.lintText(code, { filePath: resolve(repoRoot, path) });
  return result.messages.filter((message) => message.ruleId === "no-restricted-imports");
}

test("plugin renderer and SDK code cannot import host source or host-only SDK internals", async () => {
  const hostImports = [
    'import { panelTitleClass } from "../../../apps/desktop/renderer/src/shared/styles";',
    'import type { SettingsFormData } from "../../../apps/desktop/src/bridge/shared";',
    'export { createFeedbackRecorder } from "../../../../apps/desktop/renderer/src/shared/testing/feedbackRecorder";',
    'import { menuItemClass } from "@yinfengwindy/shiori-sdk/host-internal";',
  ];
  for (const path of ["plugins/boundary_probe/ui/probe.tsx", "plugins/boundary_probe/background/probe.ts", "plugins/boundary_probe/surface/nested/probe.ts", "plugins/boundary_probe/shared/probe.ts", "packages/sdk/src/probe.ts"]) {
    for (const code of hostImports) assert.equal((await boundaryViolations(code, path)).length, 1, `${path}: ${code}`);
    assert.deepEqual(await boundaryViolations('import { PluginBridgeError } from "@yinfengwindy/shiori-sdk";\nimport { deferred } from "@yinfengwindy/shiori-sdk/testing";', path), []);
  }
});

test("every plugin entry and SDK module rejects host global bridge access, including type-only access", async () => {
  const examples = [
    "window.miraDesktop.startVoicePress();",
    'window["miraDesktop"].voiceCancel();',
    "globalThis.miraDesktop.onEvent(() => {});",
    "const { miraDesktop: bridge } = window;",
    'type Bridge = Window["miraDesktop"];',
    "let bridge: DesktopApi;",
  ];
  for (const path of ["plugins/desktop_pet/surface/probe.ts", "plugins/boundary_probe/ui/probe.ts", "plugins/boundary_probe/background/probe.ts", "plugins/boundary_probe/shared/probe.ts", "packages/sdk/src/probe.ts"]) {
    for (const code of examples) {
      const [result] = await eslint.lintText(code, { filePath: resolve(repoRoot, path) });
      assert.ok(result.messages.some((entry) => entry.ruleId === "no-restricted-syntax"), `${path}: ${code}`);
    }
  }
});
