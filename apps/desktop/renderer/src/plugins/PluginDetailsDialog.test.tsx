import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { PluginSummary } from "./pluginBridgeClient";

let Dialog: typeof import("@base-ui/react/dialog").Dialog;
let PluginDetailsDialog: typeof import("./PluginDetailsDialog").PluginDetailsDialog;
before(async () => {
  const view = await mountTestComponent(null);
  ({ Dialog } = await import("@base-ui/react/dialog"));
  ({ PluginDetailsDialog } = await import("./PluginDetailsDialog"));
  await view.cleanup();
});

const plugin: PluginSummary = {
  id: "external", candidateId: "workspace/external", name: "External", version: "1.0.0",
  directory: "C:/workspace/plugins/external", description: "Line one\nLine two", source: "workspace",
  enabled: false, canToggle: false, state: "BLOCKED", error: "Activation failed",
  diagnostic: { code: "missing_dependency", stage: "setup", field: "dependencies", reason: "Dependency is unavailable", path: "C:/workspace/plugins/external/manifest.yaml", state: "BLOCKED" },
  hasConfigSchema: false, capabilities: [], channels: [], category: "feature", supportsHotUnload: true, pendingRendererKinds: [],
};

test("details expose candidate metadata and full diagnostics within a scrollable body", async () => {
  let updates = 0;
  let removals = 0;
  const view = await mountTestComponent(<Dialog.Root open>
    <PluginDetailsDialog plugin={plugin} busy={false} error="" onUpdate={() => { updates++; }} onUninstall={() => { removals++; }} />
  </Dialog.Root>);
  try {
    const dialog = document.querySelector('[role="dialog"]')!;
    assert.equal(document.getElementById(dialog.getAttribute("aria-labelledby")!)?.textContent, "External");
    for (const value of [plugin.id, plugin.version, plugin.directory, plugin.description, "工作区", "missing_dependency", "Dependency is unavailable", plugin.diagnostic!.path, plugin.error]) {
      assert.ok(dialog.textContent?.includes(value), `missing detail ${value}`);
    }
    assert.ok(dialog.querySelector(".overflow-y-auto.min-h-0"));
    assert.ok(dialog.className.includes("max-h-[calc(100dvh-2rem)]"));
    const actions = Array.from(dialog.querySelectorAll<HTMLButtonElement>("button"));
    await act(async () => actions.find((button) => button.textContent === "从 ZIP 更新")!.click());
    await act(async () => actions.find((button) => button.textContent === "卸载插件")!.click());
    assert.equal(updates, 1);
    assert.equal(removals, 1);
  } finally { await view.cleanup(); }
});

test("ineligible candidates keep details available without package actions", async () => {
  const view = await mountTestComponent(null);
  try {
    for (const candidate of [
      { ...plugin, source: "builtin" as const },
      { ...plugin, state: "CONFLICT" },
      { ...plugin, packageInstalled: false, state: "FAILED" },
      { ...plugin, pendingOperation: "install" as const },
      { ...plugin, pendingOperation: "update" as const, pendingVersion: "2.0.0" },
      { ...plugin, pendingOperation: "uninstall" as const },
      { ...plugin, trustPendingRestart: true },
    ]) {
      await view.render(<Dialog.Root open>
        <PluginDetailsDialog plugin={candidate} busy={false} error="" onUpdate={() => assert.fail("unsafe update")} onUninstall={() => assert.fail("unsafe removal")} />
      </Dialog.Root>);
      const dialog = document.querySelector('[role="dialog"]')!;
      assert.ok(dialog.textContent?.includes(candidate.directory));
      assert.doesNotMatch(dialog.textContent ?? "", /从 ZIP 更新|卸载插件/);
      if (candidate.pendingOperation === "update") assert.match(dialog.textContent ?? "", /1\.0\.0 → 2\.0\.0/);
    }
  } finally { await view.cleanup(); }
});

test("in-flight changes disable detail actions and retained failures remain visible", async () => {
  const view = await mountTestComponent(<Dialog.Root open>
    <PluginDetailsDialog plugin={{ ...plugin, packageOperationError: "disk full", rendererError: "UI unavailable" }} busy error="bridge unavailable" onUpdate={() => assert.fail("busy update")} onUninstall={() => assert.fail("busy removal")} />
  </Dialog.Root>);
  try {
    const dialog = document.querySelector('[role="dialog"]')!;
    assert.match(dialog.textContent ?? "", /disk full/);
    assert.match(dialog.textContent ?? "", /界面加载失败 · UI unavailable/);
    assert.match(dialog.textContent ?? "", /bridge unavailable/);
    for (const button of Array.from(dialog.querySelectorAll<HTMLButtonElement>("button"))) assert.equal(button.disabled, true);
  } finally { await view.cleanup(); }
});
