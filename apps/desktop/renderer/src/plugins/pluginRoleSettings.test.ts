import assert from "node:assert/strict";
import { test } from "node:test";
import { pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { buildPluginRoleDraftUpdates, notifyPluginRoleSaved, pluginRoleSettingsDirty, readPluginRoleSettings, writePluginRoleSettings } from "./pluginRoleSettings";

test("role extensions round trip their keys without replacing another module's values", () => {
  pluginRoleSettingsRegistry.register({ pluginId: "sample", Component: () => null,
    read: (runtime) => ({ selected: Boolean(runtime.sample_selected) }),
    write: (runtime, values) => ({ ...runtime, sample_selected: values.selected }),
  });
  try {
    const runtime = { sample_selected: true, mood: "happy" };
    const drafts = readPluginRoleSettings(runtime);
    assert.equal(pluginRoleSettingsDirty(drafts, runtime), false);
    const changed = { ...drafts, sample: { selected: false } };
    assert.equal(pluginRoleSettingsDirty(changed, runtime), true);
    assert.deepEqual(writePluginRoleSettings(runtime, changed), { sample_selected: false, mood: "happy" });
  } finally {
    pluginRoleSettingsRegistry.unregister("sample");
  }
});


test("independent drafts keep explicit save semantics without touching runtime_config", async () => {
  const { setPluginEnabledSnapshot, resetPluginEnabledStateForTests } = await import("./pluginEnabledStateStore");
  const saved: unknown[] = [];
  pluginRoleSettingsRegistry.register({ pluginId: "independent", storage: "plugin", Component: () => null,
    read: (state) => ({ enabled: state.enabled === true }),
    afterSave: async (values) => { saved.push(values); },
  });
  setPluginEnabledSnapshot([{ id: "independent", enabled: true, state: "ACTIVE" }]);
  try {
    const runtime = { other: 42 };
    const snapshot = { independent: { enabled: false, available: true } };
    const draft = readPluginRoleSettings(runtime, snapshot);
    assert.deepEqual(draft, { independent: { enabled: false } });
    assert.equal(pluginRoleSettingsDirty(draft, runtime, snapshot), false);
    const edited = { independent: { enabled: true } };
    assert.equal(pluginRoleSettingsDirty(edited, runtime, snapshot), true);
    assert.deepEqual(writePluginRoleSettings(runtime, edited), runtime);
    assert.deepEqual(buildPluginRoleDraftUpdates(edited, snapshot), edited);
    assert.deepEqual(saved, []);
    await notifyPluginRoleSaved(edited, runtime, snapshot);
    assert.deepEqual(saved, [{ enabled: true }]);
    assert.deepEqual(buildPluginRoleDraftUpdates(draft, snapshot), {});
    setPluginEnabledSnapshot([{ id: "independent", enabled: false, state: "DISABLED" }]);
    assert.deepEqual(buildPluginRoleDraftUpdates(edited, snapshot), {});
    assert.equal(pluginRoleSettingsDirty(edited, runtime, snapshot), false);
    await notifyPluginRoleSaved(edited, runtime, snapshot);
    assert.equal(saved.length, 1);
  } finally {
    pluginRoleSettingsRegistry.unregister("independent");
    resetPluginEnabledStateForTests();
  }
});
