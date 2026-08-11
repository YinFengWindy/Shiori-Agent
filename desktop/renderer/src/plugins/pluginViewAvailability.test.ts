import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createPluginCatalog } from "./pluginCatalog.js";
import { isPluginViewAvailable, shouldFallbackFromPluginView } from "./pluginViewAvailability.js";

const absentCatalog = createPluginCatalog([]);
const loadedCatalog = createPluginCatalog([{
  schema_version: 1,
  plugin_id: "novelai",
  name: "NovelAI",
  version: "1",
  description: "",
  author: "",
  capabilities: ["ui.navigation"],
  rpc_methods: [],
  ui_contributions: [{ id: "studio", slot: "navigation", title: "Studio", renderer: "novelai.image-studio", order: 1 }],
}]);

describe("pluginViewAvailability", () => {
  it("falls back from a stale plugin route only after the bridge is online", () => {
    assert.equal(shouldFallbackFromPluginView("connecting", "image-studio", absentCatalog), false);
    assert.equal(shouldFallbackFromPluginView("online", "image-studio", absentCatalog), true);
    assert.equal(shouldFallbackFromPluginView("online", "image-studio", loadedCatalog), false);
  });

  it("does not gate core routes", () => {
    assert.equal(isPluginViewAvailable("chat", absentCatalog), true);
    assert.equal(shouldFallbackFromPluginView("online", "settings", absentCatalog), false);
  });
});
