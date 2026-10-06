import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { chooseSelectOption, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { VoiceProviderDescriptor } from "../../../src/bridge/shared";
import { createSettingsDraft } from "./testFixtures";

let VoiceSettingsSection: typeof import("./VoiceSettingsSection").VoiceSettingsSection;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ VoiceSettingsSection } = await import("./VoiceSettingsSection"));
  await environment.cleanup();
});

describe("VoiceSettingsSection", () => {
  it("selects discovered providers independently and retains a disabled plugin selection", async () => {
    let draft = createSettingsDraft();
    let providers: VoiceProviderDescriptor[] = [
      { id: "local-asr", label: "Local ASR", kind: "asr", plugin_id: "local-asr", available: true, capabilities: { emotions: [], voice_cloning: false } },
      { id: "local-tts", label: "Local TTS", kind: "tts", plugin_id: "local-tts", available: true, capabilities: { emotions: ["bright"], voice_cloning: false } },
    ];
    const listeners = new Set<(event: BridgeEvent) => void>();
    const render = () => <VoiceSettingsSection draft={draft} subsectionId="provider" updateDraft={(mutate) => { draft = mutate(draft); }} />;
    const view = await mountTestComponent(render(), { windowGlobals: { miraDesktop: {
      invoke: async ({ method }: { method: string }) => ({ id: "r", type: "response", method, error: null, payload: { providers } }),
      onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    } } });
    try {
      await chooseSelectOption("语音识别服务商", "Local ASR");
      await view.render(render());
      await chooseSelectOption("语音合成服务商", "Local TTS");
      await view.render(render());
      assert.equal(draft.voice.asrProvider, "local-asr");
      assert.equal(draft.voice.ttsProvider, "local-tts");
      assert.doesNotMatch(view.container.textContent ?? "", /SecretId|SecretKey|API Key|模型|音量/);
      providers = [providers[0]];
      await act(async () => {
        for (const listener of listeners) listener({ id: "e", type: "event", method: "plugins.changed", payload: {} });
      });
      assert.equal(draft.voice.ttsProvider, "local-tts");
      assert.match(view.container.querySelector('[aria-label="语音合成服务商"]')?.textContent ?? "", /local-tts（不可用）/);
    } finally { await view.cleanup(); }
  });
});
