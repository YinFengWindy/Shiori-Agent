import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SettingsFormData } from "../../../src/shared.js";
import { readPluginSetting, writePluginSetting } from "./pluginSettingsSchema.js";

const draft = {
  integrations: {
    novelaiEnabled: false,
    novelaiToken: "token",
  },
  advanced: {
    devMode: false,
  },
} as SettingsFormData;

describe("pluginSettingsSchema", () => {
  it("reads and immutably updates an existing manifest path", () => {
    const updated = writePluginSetting(draft, "integrations.novelaiEnabled", true);

    assert.equal(readPluginSetting(updated, "integrations.novelaiEnabled"), true);
    assert.equal(readPluginSetting(draft, "integrations.novelaiEnabled"), false);
    assert.notEqual(updated.integrations, draft.integrations);
    assert.equal(updated.advanced, draft.advanced);
  });

  it("fails fast when a manifest points outside the settings contract", () => {
    assert.throws(
      () => writePluginSetting(draft, "integrations.missing", true),
      /Unknown plugin settings path/,
    );
    assert.equal(readPluginSetting(draft, "integrations.missing"), undefined);
  });
});
