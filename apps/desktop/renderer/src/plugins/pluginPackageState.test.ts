import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginSummary } from "./pluginBridgeClient";
import { canManagePluginPackage, pluginDetailsCandidate } from "./pluginPackageState";

const installed: PluginSummary = {
  id: "demo", candidateId: "workspace/demo", directory: "workspace/demo", source: "workspace", name: "Demo", version: "1.0.0",
  description: "", enabled: true, canToggle: true, state: "ACTIVE", error: "", diagnostic: null, hasConfigSchema: false, supportsHotUnload: true, pendingRendererKinds: [],
};

test("only installed unique external packages without queued changes are manageable", () => {
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

test("details follow the exact candidate's refreshed status without selecting another directory", () => {
  const other = { ...installed, id: "other", candidateId: "workspace/other" };
  const pending = { ...installed, pendingOperation: "update" as const };
  const builtin = { ...installed, source: "builtin" as const, candidateId: "builtin/demo" };
  const conflict = { ...installed, state: "CONFLICT" };
  assert.equal(pluginDetailsCandidate([installed, other], installed.candidateId), installed);
  assert.equal(pluginDetailsCandidate([other], installed.candidateId), null);
  assert.equal(pluginDetailsCandidate([pending, other], installed.candidateId), pending);
  assert.equal(pluginDetailsCandidate([builtin, conflict], builtin.candidateId), builtin);
  assert.equal(pluginDetailsCandidate([builtin, conflict], conflict.candidateId), conflict);
  assert.equal(pluginDetailsCandidate([installed], null), null);
  assert.equal(pluginDetailsCandidate(null, installed.candidateId), null);
});
