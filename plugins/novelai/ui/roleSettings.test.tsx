import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { PluginRoleValues } from "@shiori/plugin-sdk";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { NovelAiRoleSettings, novelAiRoleSettings } from "./roleSettings";

// The role editor's draft bookkeeping (dirty check, explicit Save, dropping a
// disabled plugin's edits) is the host's, covered by pluginRoleSettings.test.ts;
// this checks what novelai contributes to it.

test("NovelAI CG preference is read from its own snapshot and never written into runtime_config", () => {
  // `storage: "plugin"` with no `write`: the role's runtime_config is never touched.
  assert.equal(novelAiRoleSettings.storage, "plugin");
  assert.equal("write" in novelAiRoleSettings, false);
  // No save of its own: the value only persists through the editor's explicit Save.
  assert.equal("afterSave" in novelAiRoleSettings, false);

  const snapshot = { autoSceneCgEnabled: false };
  assert.deepEqual(novelAiRoleSettings.read(snapshot), { autoSceneCgEnabled: false });
  assert.deepEqual(novelAiRoleSettings.read({ autoSceneCgEnabled: true, available: true }), { autoSceneCgEnabled: true });
  assert.deepEqual(novelAiRoleSettings.read({ autoSceneCgEnabled: "yes" }), { autoSceneCgEnabled: false }, "only a real true enables it");
  assert.deepEqual(snapshot, { autoSceneCgEnabled: false }, "reading leaves the snapshot as it was");
});

test("NovelAI CG toggle only edits the role draft", async () => {
  const changes: PluginRoleValues[] = [];
  const values = { autoSceneCgEnabled: false };
  const view = await mountTestComponent(<NovelAiRoleSettings values={values} onChange={(next) => changes.push(next)} />);
  try {
    const toggle = view.container.querySelector<HTMLButtonElement>('[aria-label="自动场景 CG"]');
    assert.equal(toggle?.getAttribute("aria-checked"), "false");
    await act(async () => { toggle?.click(); });
    assert.deepEqual(changes, [{ autoSceneCgEnabled: true }]);
    assert.deepEqual(values, { autoSceneCgEnabled: false }, "the edit is a new draft, not a mutation of the current one");
  } finally { await view.cleanup(); }
});
