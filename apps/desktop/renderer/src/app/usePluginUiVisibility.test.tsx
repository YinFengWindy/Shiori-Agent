import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import {
  resetPluginEnabledStateForTests,
  setPluginEnabledSnapshot,
} from "../plugins/pluginEnabledStateStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { usePluginUiVisibility, type PluginUiVisibility } from "./usePluginUiVisibility";

function registerDemoPlugin(pluginId: string) {
  pluginUiRegistry.registerNavPage({
    slot: "nav.page", id: pluginId, label: pluginId, pluginId, Component: () => null,
  });
  pluginUiRegistry.registerSettingsSection({
    kind: "standalone", slot: "settings.section", id: pluginId, label: pluginId,
    subsections: [], pluginId, Component: () => null,
  });
}

async function mountHarness() {
  const renders: PluginUiVisibility[] = [];
  let forceRerender!: () => void;

  function Harness() {
    const [, setTick] = useState(0);
    forceRerender = () => setTick((n) => n + 1);
    const visibility = usePluginUiVisibility();
    renders.push(visibility);
    return null;
  }

  const view = await mountTestComponent(<Harness />);
  return { view, renders, rerender: () => { forceRerender(); } };
}

describe("usePluginUiVisibility", () => {
  it("hides a plugin's nav.page and settings.section as soon as it is disabled", async () => {
    resetPluginEnabledStateForTests();
    const pluginId = "demo-visibility-a";
    registerDemoPlugin(pluginId);
    setPluginEnabledSnapshot([{ id: pluginId, enabled: true, state: "ACTIVE" }]);

    const { view, renders } = await mountHarness();
    try {
      const enabled = renders.at(-1)!;
      assert.ok(enabled.pluginNavPages.some((entry) => entry.id === pluginId));
      assert.ok(enabled.settingsSidebarSections.some((entry) => entry.id === pluginId));
      assert.equal(enabled.isSectionVisible(pluginId), true);
      assert.equal(enabled.resolveVisibleNavPage(pluginId)?.id, pluginId);

      await act(async () => { setPluginEnabledSnapshot([{ id: pluginId, enabled: false, state: "DISABLED" }]); });

      const disabled = renders.at(-1)!;
      assert.ok(!disabled.pluginNavPages.some((entry) => entry.id === pluginId));
      assert.ok(!disabled.settingsSidebarSections.some((entry) => entry.id === pluginId));
      assert.equal(disabled.isSectionVisible(pluginId), false);
      assert.equal(disabled.resolveVisibleNavPage(pluginId), undefined);
    } finally {
      await view.cleanup();
      pluginUiRegistry.unregisterPlugin(pluginId);
      resetPluginEnabledStateForTests();
    }
  });

  it("keeps the same callback/array references across an unrelated re-render (no memoized-consumer staleness)", async () => {
    resetPluginEnabledStateForTests();
    const pluginId = "demo-visibility-b";
    registerDemoPlugin(pluginId);
    setPluginEnabledSnapshot([{ id: pluginId, enabled: true, state: "ACTIVE" }]);

    const { view, renders, rerender } = await mountHarness();
    try {
      const first = renders.at(-1)!;
      await act(async () => { rerender(); });
      const second = renders.at(-1)!;

      assert.equal(second.pluginNavPages, first.pluginNavPages);
      assert.equal(second.settingsSidebarSections, first.settingsSidebarSections);
      assert.equal(second.isSectionVisible, first.isSectionVisible);
      assert.equal(second.resolveVisibleNavPage, first.resolveVisibleNavPage);

      // But once the underlying plugin-enabled state actually changes, every
      // derived value gets a fresh identity — this is what lets a consumer
      // safely depend on these references instead of reading stale results.
      await act(async () => { setPluginEnabledSnapshot([{ id: pluginId, enabled: false, state: "DISABLED" }]); });
      const third = renders.at(-1)!;
      assert.notEqual(third.isSectionVisible, first.isSectionVisible);
    } finally {
      await view.cleanup();
      pluginUiRegistry.unregisterPlugin(pluginId);
      resetPluginEnabledStateForTests();
    }
  });
});
