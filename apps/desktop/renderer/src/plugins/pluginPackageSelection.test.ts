import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginSummary } from "./pluginBridgeClient";
import { canManagePluginPackage, selectedPluginPackage } from "./pluginPackageSelection";

const installed: PluginSummary = {
  id: "demo", candidateId: "workspace/demo", directory: "workspace/demo", source: "workspace", name: "Demo", version: "1.0.0",
  description: "", enabled: true, canToggle: true, state: "ACTIVE", error: "", diagnostic: null, hasConfigSchema: false, supportsHotUnload: true, pendingRendererKinds: [],
};

test("only installed unique external packages without queued changes are selectable", () => {
  assert.equal(canManagePluginPackage(installed), true);
  for (const candidate of [
    { ...installed, source: "builtin" as const },
    { ...installed, state: "CONFLICT" },
    { ...installed, pendingOperation: "update" as const },
    { ...installed, pendingOperation: "uninstall" as const },
    { ...installed, trustPendingRestart: true },
    { ...installed, state: "FAILED", packageInstalled: false },
  ]) assert.equal(canManagePluginPackage(candidate), false);
});

test("a removed or newly pending selection never targets another plugin", () => {
  const other = { ...installed, id: "other", candidateId: "workspace/other" };
  assert.equal(selectedPluginPackage([installed, other], installed.candidateId), installed);
  assert.equal(selectedPluginPackage([other], installed.candidateId), null);
  assert.equal(selectedPluginPackage([{ ...installed, pendingOperation: "update" }, other], installed.candidateId), null);
  assert.equal(selectedPluginPackage([installed], null), null);
});
