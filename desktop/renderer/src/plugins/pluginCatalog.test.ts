import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createPluginCatalog } from "./pluginCatalog";

describe("createPluginCatalog", () => {
  it("filters and orders contributions by fixed slot", () => {
    const catalog = createPluginCatalog([
      {
        schema_version: 1,
        plugin_id: "sample",
        name: "Sample",
        version: "1",
        description: "",
        author: "",
        capabilities: [],
        rpc_methods: [],
        ui_contributions: [
          { id: "later", slot: "navigation", title: "Later", renderer: "sample.later", order: 20 },
          { id: "settings", slot: "settings", title: "Settings", renderer: "sample.settings", order: 1 },
          { id: "earlier", slot: "navigation", title: "Earlier", renderer: "sample.earlier", order: 10 },
        ],
      },
    ]);
    assert.deepEqual(catalog.contributions("navigation").map(({ contribution }) => contribution.id), ["earlier", "later"]);
  });

  it("preserves validated declarative settings schema", () => {
    const catalog = createPluginCatalog([{
      schema_version: 1,
      plugin_id: "sample",
      name: "Sample",
      version: "1",
      description: "",
      author: "",
      capabilities: ["ui.settings"],
      rpc_methods: [],
      ui_contributions: [{
        id: "settings",
        slot: "settings",
        title: "Settings",
        renderer: "schema.settings",
        order: 1,
        settings_schema: [{ id: "enabled", label: "Enabled", type: "boolean", config_path: "integrations.sampleEnabled" }],
      }],
    }]);

    assert.equal(catalog.contributions("settings")[0]?.contribution.settings_schema?.[0]?.config_path, "integrations.sampleEnabled");
  });
});
