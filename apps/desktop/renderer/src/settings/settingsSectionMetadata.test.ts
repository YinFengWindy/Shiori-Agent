/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry.js";
import {
  createInitialSettingsSubsectionState,
  getSettingsSubsections,
  resolveSettingsSubsectionId,
} from "./settingsSectionMetadata.js";

afterEach(() => {
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "novelai");
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "qqbot");
});

describe("settingsSectionMetadata", () => {
  it("keeps every configured subsection attached to its owning domain", () => {
    assert.deepEqual(getSettingsSubsections("models").map((item) => item.id), ["catalog"]);
    assert.deepEqual(getSettingsSubsections("channels").map((item) => item.id), ["telegram", "qq"]);
  });

  it("falls back to the first subsection when persisted selection is invalid", () => {
    const active = createInitialSettingsSubsectionState();
    active.models = "removed-model-section";

    assert.equal(resolveSettingsSubsectionId("models", active), "catalog");
  });

  it("issue #230: appends a settings.subsection nested under a parent to that parent's subtab list", () => {
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection", parentId: "plugins", id: "novelai", label: "NovelAI",
      pluginId: "novelai", Component: () => null,
    });

    assert.deepEqual(getSettingsSubsections("plugins").map((item) => item.id), ["list", "novelai"]);
    // A section with no nested subtabs is unaffected.
    assert.deepEqual(getSettingsSubsections("models").map((item) => item.id), ["catalog"]);
  });

  it("issue #230 AC 3: filters a nested subtab out while its owning plugin is disabled", () => {
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection", parentId: "plugins", id: "novelai", label: "NovelAI",
      pluginId: "novelai", Component: () => null,
    });

    const isPluginEnabled = () => false;
    assert.deepEqual(getSettingsSubsections("plugins", isPluginEnabled).map((item) => item.id), ["list"]);
    assert.equal(resolveSettingsSubsectionId("plugins", { plugins: "novelai" }, isPluginEnabled), "list");
  });
});
