/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry.js";
import { listSettingsSidebarSections } from "./SettingsSidebar.js";

afterEach(() => {
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "novelai");
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "qqbot");
});

describe("listSettingsSidebarSections (issue #230 AC 1)", () => {
  it("stays exactly the seven built-ins, even with plugin settings subtabs registered", () => {
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection", parentId: "plugins", id: "novelai", label: "NovelAI",
      pluginId: "novelai", Component: () => null,
    });
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection", parentId: "plugins", id: "qqbot", label: "QQBot",
      pluginId: "qqbot", Component: () => null,
    });

    assert.deepEqual(
      listSettingsSidebarSections().map((section) => section.id),
      ["models", "channels", "memory", "voice", "advanced", "plugins", "about"],
    );
  });
});
