import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { applyPluginUiModules, type PluginUiModule } from "./pluginUiModuleContract.js";
import { pluginUiRegistry } from "./pluginUiRegistry.js";
import {
  resetPluginSettingsAutoRegistrationForTests,
  synchronizePluginSettingsAutoRegistration,
} from "./pluginSettingsAutoRegistration.js";

afterEach(() => {
  resetPluginSettingsAutoRegistrationForTests();
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "auto-a");
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "auto-b");
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "handwritten");
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "novelai");
  pluginUiRegistry.unregisterSettingsSubsection("plugins", "qqbot");
});

describe("synchronizePluginSettingsAutoRegistration (issue #230 AC 5/6)", () => {
  it("registers a schema-driven subtab for a roster plugin with a config schema and no hand-written contribution", () => {
    synchronizePluginSettingsAutoRegistration([
      { id: "auto-a", name: "Auto Plugin A", hasConfigSchema: true },
    ]);

    const entry = pluginUiRegistry.getSettingsSubsection("plugins", "auto-a");
    assert.ok(entry, "expected an auto-registered subtab");
    assert.equal(entry?.label, "Auto Plugin A");
    assert.equal(entry?.pluginId, "auto-a");
  });

  it("ignores a roster plugin without a config schema", () => {
    synchronizePluginSettingsAutoRegistration([
      { id: "auto-b", name: "No Schema", hasConfigSchema: false },
    ]);

    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "auto-b"), undefined);
  });

  it("registers an account provider even without a config schema", () => {
    synchronizePluginSettingsAutoRegistration([
      { id: "auto-b", name: "Account provider", hasConfigSchema: false, capabilities: ["accounts"] },
    ]);
    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "auto-b")?.pluginId, "auto-b");
  });

  it("never overwrites a hand-written settings.section already registered for the same plugin id", () => {
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection", parentId: "plugins", id: "handwritten", label: "Hand Written",
      pluginId: "handwritten", Component: () => null,
    });

    synchronizePluginSettingsAutoRegistration([
      { id: "handwritten", name: "Auto Label Would Be This", hasConfigSchema: true },
    ]);

    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "handwritten")?.label, "Hand Written");
  });

  it("warns about a hand-written conflict only once per plugin id, not on every refresh", () => {
    pluginUiRegistry.registerSettingsSubsection({
      slot: "settings.subsection", parentId: "plugins", id: "handwritten", label: "Hand Written",
      pluginId: "handwritten", Component: () => null,
    });
    const plugin = { id: "handwritten", name: "Auto Label Would Be This", hasConfigSchema: true };
    const warnings: unknown[][] = [];
    const originalWarn = console.warn;
    console.warn = (...args: unknown[]) => { warnings.push(args); };
    try {
      // A conflict like this is a legitimate, permanent configuration (a
      // plugin that ships both config_model and a hand-written
      // settingsSection, e.g. NovelAI) — every roster refresh (every plugin
      // toggle, every settings apply) must not re-log it forever.
      synchronizePluginSettingsAutoRegistration([plugin]);
      synchronizePluginSettingsAutoRegistration([plugin]);
      synchronizePluginSettingsAutoRegistration([plugin]);
    } finally {
      console.warn = originalWarn;
    }

    assert.equal(warnings.length, 1);
    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "handwritten")?.label, "Hand Written");
  });

  it("is idempotent across repeated refreshes (no duplicate-id warning spam from re-registering itself)", () => {
    const plugin = { id: "auto-a", name: "Auto Plugin A", hasConfigSchema: true };
    synchronizePluginSettingsAutoRegistration([plugin]);
    const firstComponent = pluginUiRegistry.getSettingsSubsection("plugins", "auto-a")?.Component;

    synchronizePluginSettingsAutoRegistration([plugin]);
    const secondComponent = pluginUiRegistry.getSettingsSubsection("plugins", "auto-a")?.Component;

    // Re-running with the same roster must not re-register (a different
    // Component instance would mean it re-registered, which would also mean
    // the registry's own duplicate-id guard silently discarded the attempt
    // instead of this function recognizing it already owns the id).
    assert.equal(firstComponent, secondComponent);
  });

  it("removes the auto-registered subtab once the plugin drops off the roster", () => {
    const plugin = { id: "auto-a", name: "Auto Plugin A", hasConfigSchema: true };
    synchronizePluginSettingsAutoRegistration([plugin]);
    assert.ok(pluginUiRegistry.getSettingsSubsection("plugins", "auto-a"));

    synchronizePluginSettingsAutoRegistration([]);

    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "auto-a"), undefined);
  });

  it("removes the auto-registered subtab once the plugin stops declaring a config schema", () => {
    synchronizePluginSettingsAutoRegistration([{ id: "auto-a", name: "Auto Plugin A", hasConfigSchema: true }]);
    assert.ok(pluginUiRegistry.getSettingsSubsection("plugins", "auto-a"));

    synchronizePluginSettingsAutoRegistration([{ id: "auto-a", name: "Auto Plugin A", hasConfigSchema: false }]);

    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "auto-a"), undefined);
  });

  it("falls back to the plugin id when the roster name is empty", () => {
    synchronizePluginSettingsAutoRegistration([{ id: "auto-a", name: "", hasConfigSchema: true }]);

    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "auto-a")?.label, "auto-a");
  });

  it("pins qqbot's real subtab label to its manifest display_name, not its lowercase directory id", () => {
    // Regression coverage for issue #230 AC 7: qqbot's manifest.yaml has no
    // `display_name`, so `plugin_management.py`'s `display_name or record.name`
    // fallback previously emitted the plugin's directory name verbatim
    // ("qqbot") once `plugins/qqbot/ui/index.tsx`'s hardcoded `label: "QQBot"`
    // was deleted — silently lowercasing a user-visible tab. The fixture
    // below is the roster shape the backend emits now that
    // `plugins/qqbot/manifest.yaml` declares `display_name: QQBot`; if a
    // future edit drops that field, the backend goes back to emitting
    // "qqbot" and this test fails loudly instead of the tab quietly
    // regressing again.
    synchronizePluginSettingsAutoRegistration([{ id: "qqbot", name: "QQBot", hasConfigSchema: true }]);

    assert.equal(pluginUiRegistry.getSettingsSubsection("plugins", "qqbot")?.label, "QQBot");
  });

  it("NovelAI (hand-written schema settingsSection + navPage) ends up with exactly one settings subtab, not two", () => {
    // Mirrors real production ordering: the build-time glob (pluginUiModules.ts)
    // registers every hand-written module before the roster's first refresh
    // ever runs auto-registration.
    const modules: Record<string, { default: PluginUiModule }> = {
      "/plugins/novelai/ui/index.tsx": {
        default: {
          pluginId: "novelai",
          settingsSection: { kind: "schema", label: "NovelAI" },
          navPage: { label: "生图", component: () => null },
        },
      },
    };
    applyPluginUiModules(modules);

    synchronizePluginSettingsAutoRegistration([
      { id: "novelai", name: "NovelAI 生图", hasConfigSchema: true },
    ]);

    const subtabs = pluginUiRegistry.listSettingsSubsections("plugins").filter((entry) => entry.pluginId === "novelai");
    assert.equal(subtabs.length, 1);
    assert.equal(subtabs[0]?.label, "NovelAI", "the hand-written label must win, not the auto-registration one");
  });
});
