import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  guardedNavPageSelect,
  PluginUiRegistry,
  type NavPageEntry,
  type RoleAssetsPanelEntry,
  type SettingsSubsectionEntry,
  type StandaloneSettingsSectionEntry,
} from "./pluginUiRegistry.js";

function standaloneSection(id: string, pluginId?: string): StandaloneSettingsSectionEntry {
  return {
    kind: "standalone",
    slot: "settings.section",
    id,
    label: id,
    subsections: [],
    pluginId,
    Component: () => null,
  };
}

function subsection(parentId: string, id: string, pluginId?: string): SettingsSubsectionEntry {
  return { slot: "settings.subsection", parentId, id, label: id, pluginId, Component: () => null };
}

function navPage(id: string, pluginId?: string): NavPageEntry {
  return { slot: "nav.page", id, label: id, pluginId, Component: () => null };
}

function roleAssetsPanel(id: string, pluginId?: string): RoleAssetsPanelEntry {
  return { slot: "role.assets", id, pluginId, Component: () => null };
}

describe("PluginUiRegistry", () => {
  it("lists built-in entries before plugin entries, each in registration order", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSection(standaloneSection("plugin-a", "a"));
    registry.registerSettingsSection(standaloneSection("builtin-1"), "builtin");
    registry.registerSettingsSection(standaloneSection("builtin-2"), "builtin");
    registry.registerSettingsSection(standaloneSection("plugin-b", "b"));

    const ids = registry.listSettingsSections().map((entry) => entry.id);
    assert.deepEqual(ids, ["builtin-1", "builtin-2", "plugin-a", "plugin-b"]);
  });

  it("skips a duplicate id instead of overwriting the first registration", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSection(standaloneSection("models"), "builtin");
    registry.registerSettingsSection(standaloneSection("models", "intruder"));

    const entries = registry.listSettingsSections();
    assert.equal(entries.length, 1);
    assert.equal(entries[0]?.pluginId, undefined);
  });

  it("filters plugin-owned nav pages by enabled state while always keeping built-ins", () => {
    const registry = new PluginUiRegistry();
    registry.registerNavPage(navPage("core"), "builtin");
    registry.registerNavPage(navPage("enabled-plugin", "a"));
    registry.registerNavPage(navPage("disabled-plugin", "b"));

    const ids = registry.listNavPages((pluginId) => pluginId === "a").map((entry) => entry.id);
    assert.deepEqual(ids, ["core", "enabled-plugin"]);
  });

  it("removes every contribution owned by a plugin on unregister", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSection(standaloneSection("section-a", "a"));
    registry.registerNavPage(navPage("page-a", "a"));
    registry.registerNavPage(navPage("page-b", "b"));
    registry.registerRoleMemoryPanel({ slot: "role.memory", id: "a", pluginId: "a", Component: () => null });

    registry.unregisterPlugin("a");

    assert.equal(registry.getSettingsSection("section-a"), undefined);
    assert.equal(registry.getNavPage("page-a"), undefined);
    assert.notEqual(registry.getNavPage("page-b"), undefined);
    assert.equal(registry.getRoleMemoryPanel("a", () => true), undefined);
  });

  it("selects only the configured enabled role.memory contribution", () => {
    const registry = new PluginUiRegistry();
    registry.registerRoleMemoryPanel({ slot: "role.memory", id: "default_memory", pluginId: "default_memory", Component: () => null });
    registry.registerRoleMemoryPanel({ slot: "role.memory", id: "akasha", pluginId: "akasha", Component: () => null });

    assert.equal(registry.getRoleMemoryPanel("akasha", (id) => id === "akasha")?.id, "akasha");
    assert.equal(registry.getRoleMemoryPanel("akasha", () => false), undefined);
    assert.equal(registry.getRoleMemoryPanel("missing", () => true), undefined);
  });
});

describe("PluginUiRegistry settings.subsection nesting (issue #230)", () => {
  it("lists a parent's subtabs built-in-first, in registration order", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSubsection(subsection("plugins", "list"), "builtin");
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "novelai"));
    registry.registerSettingsSubsection(subsection("plugins", "qqbot", "qqbot"));

    assert.deepEqual(
      registry.listSettingsSubsections("plugins").map((entry) => entry.id),
      ["list", "novelai", "qqbot"],
    );
  });

  it("does not leak a top-level entry into subsections, or a subsection into top-level listings", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSection(standaloneSection("plugins"), "builtin");
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "novelai"));

    assert.deepEqual(registry.listSettingsSections().map((entry) => entry.id), ["plugins"]);
    assert.equal(registry.getSettingsSection("novelai"), undefined);
  });

  it("skips a duplicate (parentId, id) pair instead of overwriting the first registration", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "novelai"));
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "intruder"));

    const entries = registry.listSettingsSubsections("plugins");
    assert.equal(entries.length, 1);
    assert.equal(entries[0]?.pluginId, "novelai");
  });

  it("filters subtabs by enabled state while always keeping the built-in one", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSubsection(subsection("plugins", "list"), "builtin");
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "novelai"));
    registry.registerSettingsSubsection(subsection("plugins", "qqbot", "qqbot"));

    const ids = registry.listSettingsSubsections("plugins", (pluginId) => pluginId === "novelai").map((entry) => entry.id);
    assert.deepEqual(ids, ["list", "novelai"]);
  });

  it("removes a single subtab via unregisterSettingsSubsection without touching its siblings", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "novelai"));
    registry.registerSettingsSubsection(subsection("plugins", "qqbot", "qqbot"));

    registry.unregisterSettingsSubsection("plugins", "novelai");

    assert.deepEqual(registry.listSettingsSubsections("plugins").map((entry) => entry.id), ["qqbot"]);
  });

  it("unregisterPlugin also takes a plugin's own settings.subsection with it", () => {
    const registry = new PluginUiRegistry();
    registry.registerSettingsSubsection(subsection("plugins", "novelai", "novelai"));
    registry.registerSettingsSubsection(subsection("plugins", "qqbot", "qqbot"));

    registry.unregisterPlugin("novelai");

    assert.deepEqual(registry.listSettingsSubsections("plugins").map((entry) => entry.id), ["qqbot"]);
  });
});

describe("guardedNavPageSelect (issue #226 gap B)", () => {
  it("calls onSelect when the entry has no selectBlockedReason guard at all", () => {
    let selected = false;
    let blockedReason: string | null = null;
    const handler = guardedNavPageSelect({}, () => { selected = true; }, (reason) => { blockedReason = reason; });
    handler();
    assert.equal(selected, true);
    assert.equal(blockedReason, null);
  });

  it("calls onSelect when selectBlockedReason returns null", () => {
    let selected = false;
    const handler = guardedNavPageSelect(
      { selectBlockedReason: () => null },
      () => { selected = true; },
      () => { throw new Error("must not be called"); },
    );
    handler();
    assert.equal(selected, true);
  });

  it("refuses to call onSelect and hands the reason to onBlocked when selectBlockedReason returns a message", () => {
    let selected = false;
    let blockedReason: string | null = null;
    const handler = guardedNavPageSelect(
      { selectBlockedReason: () => "请先创建至少一个角色，再进入生图。" },
      () => { selected = true; },
      (reason) => { blockedReason = reason; },
    );
    handler();
    assert.equal(selected, false);
    assert.equal(blockedReason, "请先创建至少一个角色，再进入生图。");
  });

  it("role.assets panels follow the same visibility rule as every other slot", () => {
    const registry = new PluginUiRegistry();
    registry.registerRoleAssetsPanel(roleAssetsPanel("enabled-plugin", "a"));
    registry.registerRoleAssetsPanel(roleAssetsPanel("disabled-plugin", "b"));

    // Disabling a plugin must drop its panel immediately, not at next reload
    // (#174 acceptance criterion 3) — the same rule nav.page and
    // settings.section already follow.
    const ids = registry.listRoleAssetsPanels((pluginId) => pluginId === "a").map((entry) => entry.id);
    assert.deepEqual(ids, ["enabled-plugin"]);
  });

  it("a duplicate role.assets id is refused rather than shadowing the first", () => {
    const registry = new PluginUiRegistry();
    registry.registerRoleAssetsPanel(roleAssetsPanel("desktop_pet", "desktop_pet"));
    registry.registerRoleAssetsPanel(roleAssetsPanel("desktop_pet", "impostor"));

    const entries = registry.listRoleAssetsPanels();
    assert.equal(entries.length, 1);
    assert.equal(entries[0].pluginId, "desktop_pet");
  });

  it("unregistering a plugin takes its role.assets panel with the rest", () => {
    const registry = new PluginUiRegistry();
    registry.registerRoleAssetsPanel(roleAssetsPanel("a", "a"));
    registry.registerRoleAssetsPanel(roleAssetsPanel("b", "b"));
    registry.registerNavPage(navPage("a-page", "a"));

    registry.unregisterPlugin("a");

    assert.deepEqual(registry.listRoleAssetsPanels().map((entry) => entry.id), ["b"]);
    assert.deepEqual(registry.listNavPages().map((entry) => entry.id), []);
  });

});
