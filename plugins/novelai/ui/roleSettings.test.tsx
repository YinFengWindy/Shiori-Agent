import assert from "node:assert/strict";
import { test } from "node:test";
import { novelAiRoleSettings } from "./roleSettings";
import { pluginRoleSettingsRegistry } from "../../../apps/desktop/renderer/src/plugins/pluginFeatureRegistry";
import { buildPluginRoleDraftUpdates, pluginRoleSettingsDirty, readPluginRoleSettings, writePluginRoleSettings } from "../../../apps/desktop/renderer/src/plugins/pluginRoleSettings";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginEnabledStateStore";

test("NovelAI CG toggle stays in the role draft until explicit Save", () => {
  pluginRoleSettingsRegistry.register({ pluginId: "novelai", ...novelAiRoleSettings });
  setPluginEnabledSnapshot([{ id: "novelai", enabled: true, state: "ACTIVE" }]);
  try {
    const runtime = { dialogue_model_effort: "high" };
    const snapshot = { novelai: { autoSceneCgEnabled: false } };
    const draft = readPluginRoleSettings(runtime, snapshot);
    assert.deepEqual(draft, snapshot);
    assert.deepEqual(buildPluginRoleDraftUpdates(draft, snapshot), {});
    const edited = { novelai: { autoSceneCgEnabled: true } };
    assert.equal(pluginRoleSettingsDirty(edited, runtime, snapshot), true);
    assert.equal(writePluginRoleSettings(runtime, edited), runtime);
    assert.deepEqual(buildPluginRoleDraftUpdates(edited, snapshot), edited);
    assert.deepEqual(snapshot, { novelai: { autoSceneCgEnabled: false } });
    assert.deepEqual(readPluginRoleSettings(runtime, snapshot), draft);
    setPluginEnabledSnapshot([{ id: "novelai", enabled: false, state: "DISABLED" }]);
    assert.deepEqual(buildPluginRoleDraftUpdates(edited, snapshot), {});
    assert.equal(pluginRoleSettingsDirty(edited, runtime, snapshot), false);
  } finally {
    pluginRoleSettingsRegistry.unregister("novelai");
    resetPluginEnabledStateForTests();
  }
});
