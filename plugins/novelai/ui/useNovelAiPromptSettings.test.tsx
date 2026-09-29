import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { PluginBridgeError, PluginHostServicesProvider, type PluginConfigValues, type PluginHostConfig } from "@shiori/plugin-sdk";
import { createFakeHostServices, deferred, mountTestComponent, type FakeHostServicesOptions } from "@shiori/plugin-sdk/testing";
import { useNovelAiPromptSettings, type NovelAiPromptSettings } from "./useNovelAiPromptSettings";

/** Mounts the hook under fake host services; `latest()` is the settings of the last render. */
async function mountSettings(options: FakeHostServicesOptions, config: Partial<PluginHostConfig> = {}) {
  const fake = createFakeHostServices(options);
  // `config` replaces parts of the fake `host.config`, e.g. to hold the initial read.
  fake.host.config = { ...fake.host.config, ...config };
  let current: NovelAiPromptSettings | null = null;
  function Probe() {
    current = useNovelAiPromptSettings();
    return null;
  }
  const view = await mountTestComponent(<PluginHostServicesProvider services={fake.host}><Probe /></PluginHostServicesProvider>);
  const latest = () => {
    assert.ok(current);
    return current;
  };
  return { view, fake, latest };
}

/** A `saveConfig` that stores each save only when the test releases it, in call order. */
function heldSaves() {
  const held: Array<ReturnType<typeof deferred<void>>> = [];
  const saveConfig = async (patch: PluginConfigValues, current: PluginConfigValues) => {
    const gate = deferred<void>();
    held.push(gate);
    await gate.promise;
    return { ...current, ...patch };
  };
  return { held, saveConfig };
}

describe("useNovelAiPromptSettings", () => {
  it("reads the stored config on mount and resolves the model from it", async () => {
    const { view, latest } = await mountSettings({
      config: { nsfw_enabled: true, add_quality_tags: true, undesired_content_preset: 2, nsfw_model: "nai-nsfw" },
    });
    try {
      assert.equal(latest().nsfwEnabled, true);
      assert.equal(latest().addQualityTags, true);
      assert.equal(latest().undesiredContentPreset, 2);
      assert.equal(latest().model, "nai-nsfw");
    } finally { await view.cleanup(); }
  });

  it("shows an edit at once and saves it as a one-field patch", async () => {
    const saves = heldSaves();
    const { view, fake, latest } = await mountSettings({ config: { nsfw_enabled: false, default_model: "curated" }, saveConfig: saves.saveConfig });
    try {
      await act(async () => latest().setNsfwEnabled(true));
      assert.equal(latest().nsfwEnabled, true, "the switch flips before the save settles");
      assert.deepEqual(fake.calls.filter((call) => call.service === "config.save"), [{ service: "config.save", patch: { nsfw_enabled: true } }]);
      await act(async () => saves.held[0]?.resolve());
      assert.equal(latest().nsfwEnabled, true);
      assert.deepEqual(fake.config(), { nsfw_enabled: true, default_model: "curated" });
    } finally { await view.cleanup(); }
  });

  it("keeps the latest edit on screen while an earlier save's result comes back", async () => {
    const saves = heldSaves();
    const { view, fake, latest } = await mountSettings({ config: { nsfw_enabled: false }, saveConfig: saves.saveConfig });
    try {
      await act(async () => latest().setNsfwEnabled(true));
      await act(async () => latest().setNsfwEnabled(false));
      // The first save stores `true` and broadcasts it; the second edit (`false`) must not flash back.
      await act(async () => saves.held[0]?.resolve());
      assert.equal(fake.config().nsfw_enabled, true);
      assert.equal(latest().nsfwEnabled, false);
      await act(async () => saves.held[1]?.resolve());
      assert.equal(fake.config().nsfw_enabled, false);
      assert.equal(latest().nsfwEnabled, false);
    } finally { await view.cleanup(); }
  });

  it("keeps a saved value even when the host has not broadcast it yet", async () => {
    // A host whose broadcast of this save has not reached the popover: the resolved values alone must hold the switch.
    const { view, latest } = await mountSettings({ config: { nsfw_enabled: false } }, { subscribe: () => () => undefined });
    try {
      await act(async () => latest().setNsfwEnabled(true));
      assert.equal(latest().nsfwEnabled, true);
    } finally { await view.cleanup(); }
  });

  it("drops an initial read that a newer stored result overtook", async () => {
    const read = deferred<PluginConfigValues>();
    const { view, fake, latest } = await mountSettings({ config: { nsfw_enabled: false } }, { get: () => read.promise });
    try {
      // Saved elsewhere while the first read is still on its way; that read predates the save.
      await act(async () => { await fake.host.config.save({ nsfw_enabled: true }); });
      await act(async () => read.resolve({ nsfw_enabled: false }));
      assert.equal(latest().nsfwEnabled, true);
    } finally { await view.cleanup(); }
  });

  it("says why the config could not be read", async () => {
    const { view, fake } = await mountSettings({}, { get: async () => { throw new PluginBridgeError("配置文件损坏", "plugin_config_unreadable"); } });
    try {
      assert.deepEqual(fake.feedback.map(({ tone, message, options }) => [tone, message, options?.detail]), [
        ["error", "生成设置加载失败", "配置文件损坏"],
      ]);
    } finally { await view.cleanup(); }
  });

  it("follows a save made elsewhere, such as the plugin's settings tab", async () => {
    const { view, fake, latest } = await mountSettings({ config: { add_quality_tags: false } });
    try {
      await act(async () => { await fake.host.config.save({ add_quality_tags: true }); });
      assert.equal(latest().addQualityTags, true);
    } finally { await view.cleanup(); }
  });

  it("drops a rejected edit back to the stored value and says why", async () => {
    const { view, fake, latest } = await mountSettings({
      config: { undesired_content_preset: 0 },
      saveConfig: async () => { throw new PluginBridgeError("undesired_content_preset 超出范围", "plugin_config_invalid"); },
    });
    try {
      await act(async () => latest().setUndesiredContentPreset(2));
      assert.equal(latest().undesiredContentPreset, 0);
      assert.deepEqual(fake.feedback.map(({ tone, message, options }) => [tone, message, options?.detail]), [
        ["error", "生成设置保存失败", "undesired_content_preset 超出范围"],
      ]);
    } finally { await view.cleanup(); }
  });
});
