import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { PluginConfigValues } from "@shiori/plugin-sdk";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { createPluginHostConfig } from "./pluginHostConfig";
import { usePluginConfigController } from "./usePluginConfigController";

/** A preload bridge over one in-memory `plugin.config` table. */
function configBridge(table: PluginConfigValues) {
  let stored = { ...table };
  return {
    onEvent: () => () => undefined,
    invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      if (method === "plugin.config.set") stored = { ...(payload.values as PluginConfigValues) };
      else if (method !== "plugin.config.get") throw new Error(method);
      return { id: "1", type: "response", method, error: null, payload: { plugin_id: payload.plugin_id, schema: {}, values: { ...stored }, env_status: {}, generation: 1 } };
    },
  };
}

const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

test("the settings page and the plugin's host.config see each other's saves", async () => {
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: configBridge({ nsfw_enabled: false, add_quality_tags: false }) } });
  let controller!: ReturnType<typeof usePluginConfigController>;
  function SettingsPage() {
    controller = usePluginConfigController("novelai");
    return null;
  }
  try {
    await view.render(<SettingsPage />);
    await settle();
    assert.deepEqual(controller.draft, { nsfw_enabled: false, add_quality_tags: false });

    // A plugin save refreshes the host's config state.
    const config = createPluginHostConfig("novelai");
    await act(async () => { await config.save({ nsfw_enabled: true }); });
    await settle();
    assert.deepEqual(controller.draft, { nsfw_enabled: true, add_quality_tags: false });

    // And a save on the settings page reaches the plugin's subscription.
    const heard: PluginConfigValues[] = [];
    const unsubscribe = config.subscribe((values) => heard.push(values));
    await act(async () => controller.updateDraft((current) => ({ ...current, add_quality_tags: true })));
    await settle();
    unsubscribe();
    assert.deepEqual(heard, [{ nsfw_enabled: true, add_quality_tags: true }]);
  } finally { await view.cleanup(); }
});
