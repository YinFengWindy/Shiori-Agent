/// <reference types="node" />

import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { SettingsFormData } from "../../../src/bridge/shared.js";
import { mountTestComponent, chooseSelectOption } from "@shiori/sdk/testing";
import { createSettingsDraft } from "./testFixtures";

let VoiceInputSettingsSection: typeof import("./VoiceInputSettingsSection").VoiceInputSettingsSection;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ VoiceInputSettingsSection } = await import("./VoiceInputSettingsSection"));
  await environment.cleanup();
});

const draft = {
  voice: {
    enabled: true,
    hotkey: "Ctrl+Space",
    microphoneDeviceId: "",
    asrProvider: "tencent",
    asrBaseUrl: "https://asr.tencentcloudapi.com/",
    asrSecretId: "secret-id",
    asrSecretKey: "secret-key",
    ttsProvider: "minimax",
    ttsBaseUrl: "https://api.minimaxi.com/v1/t2a_v2",
    ttsModel: "speech-2.8-turbo",
    ttsApiKey: "tts-key",
    ttsVolume: 2,
  },
} satisfies Pick<SettingsFormData, "voice">;

describe("VoiceInputSettingsSection", () => {
  it("places an icon-only microphone test action beside the device picker", () => {
    const markup = renderToStaticMarkup(
      <VoiceInputSettingsSection draft={draft} updateDraft={() => undefined} />,
    );

    assert.match(markup, /麦克风设备/);
    assert.match(markup, /flex min-w-0 items-center gap-2/);
    assert.match(markup, /aria-label="测试麦克风"/);
    assert.match(markup, /title="测试麦克风"/);
    assert.doesNotMatch(markup, /刷新设备|测试录音/);
  });

  it("loads device options and writes both a chosen device and the empty system default", async () => {
    const view = await mountTestComponent(null);
    let settings = createSettingsDraft();
    Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
      listVoiceInputDevices: async () => [{ deviceId: "usb-input", label: "USB microphone" }],
    } });
    const renderFields = () => <VoiceInputSettingsSection draft={settings} updateDraft={(mutate) => { settings = mutate(settings); }} />;
    try {
      await view.render(renderFields());
      await chooseSelectOption("麦克风设备", "USB microphone");
      assert.equal(settings.voice.microphoneDeviceId, "usb-input");
      await view.render(renderFields());
      await chooseSelectOption("麦克风设备", "系统默认设备");
      assert.equal(settings.voice.microphoneDeviceId, "");
    } finally { await view.cleanup(); }
  });
});
