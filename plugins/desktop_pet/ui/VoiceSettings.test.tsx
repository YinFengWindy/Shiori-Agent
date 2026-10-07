import assert from "node:assert/strict";
import { before, test, type TestContext } from "node:test";
import { act } from "react";
import type { NativeAudioDevice, PluginServiceDescriptor } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, chooseSelectOption, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { defaultVoicePreferences, type VoicePreferences } from "../background/voice/preferences";
let VoiceSettings: typeof import("./VoiceSettings").VoiceSettings;
before(async () => { const mounted = await mountTestComponent(null); ({ VoiceSettings } = await import("./VoiceSettings")); await mounted.cleanup(); });

const asrProvider: PluginServiceDescriptor = { plugin_id: "sensevoice_asr", service_id: "asr", contract: "shiori.asr.v1", label: "SenseVoiceSmall", metadata: {} };
const ttsProvider: PluginServiceDescriptor = { plugin_id: "gpt_sovits_tts", service_id: "tts", contract: "shiori.tts.v1", label: "GPT-SoVITS", metadata: {} };
const asrRef = { plugin_id: "sensevoice_asr", service_id: "asr" };
const ttsRef = { plugin_id: "gpt_sovits_tts", service_id: "tts" };

type Setup = {
  preferences?: Partial<VoicePreferences>;
  get?: () => Promise<VoicePreferences>;
  set?: (value: VoicePreferences) => Promise<VoicePreferences>;
  asr?: PluginServiceDescriptor[];
  tts?: PluginServiceDescriptor[];
  devices?: () => Promise<NativeAudioDevice[]>;
  validate?: (hotkey: string) => Promise<void>;
};

/** Mounts the page against a fake backend; `saves` records every private write. */
async function mountSettings(setup: Setup = {}) {
  const { host, calls, uiRenders } = createFakeHostServices();
  const saves: VoicePreferences[] = [];
  const stored = { ...defaultVoicePreferences, ...setup.preferences };
  const client = createFakePluginClient({
    call: async <T,>(method: string, payload?: Record<string, unknown>) => {
      if (method === "voice.preferences.get") return (setup.get ? await setup.get() : stored) as T;
      if (method === "voice.preferences.set") {
        const value = payload as VoicePreferences;
        saves.push(value);
        return (setup.set ? await setup.set(value) : value) as T;
      }
      throw new Error(`unexpected ${method}`);
    },
    services: {
      list: async (contract: string) => ({ services: contract === "shiori.asr.v1" ? setup.asr ?? [asrProvider] : setup.tts ?? [ttsProvider] }),
      call: async <T,>() => undefined as T,
    },
    background: {
      call: async <T,>(method: string, payload?: Record<string, unknown>) => {
        if (method === "voice.devices") return (setup.devices ? await setup.devices() : [{ deviceId: "mic-1", label: "USB 麦克风" }]) as T;
        if (method === "voice.preferences.validate") { await setup.validate?.(String(payload?.hotkey)); return undefined as T; }
        throw new Error(`unexpected ${method}`);
      },
    },
  });
  const view = await mountTestComponent(<VoiceSettings client={client} host={host} subsectionId="desktop_pet" onSelectSubsection={() => {}} />);
  await act(async () => { await Promise.resolve(); });
  return { view, saves, calls, uiRenders };
}

const text = () => document.body.textContent ?? "";
const button = (label: string) => Array.from(document.querySelectorAll("button")).find((item) => item.textContent === label);
const combobox = (label: string) => document.querySelector<HTMLButtonElement>(`[role="combobox"][aria-label="${label}"]`)!;
const voiceSwitch = () => document.querySelector<HTMLButtonElement>('[role="switch"][aria-label="桌宠语音"]')!;
const tick = (t: TestContext, ms: number) => act(async () => t.mock.timers.tick(ms));

/** Opens a picker and returns the option labels on screen (a closed picker may keep its list mounted), then closes it. */
async function optionLabels(label: string) {
  await act(async () => combobox(label).click());
  const labels = Array.from(document.querySelectorAll('[role="option"]')).map((option) => option.textContent);
  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  return labels;
}

test("an edit saves itself after the quiet period, with no save button, and reports its phase to the host", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { view, saves, calls, uiRenders } = await mountSettings();
  try {
    assert.equal(button("保存"), undefined);
    await chooseSelectOption("麦克风", "USB 麦克风");
    assert.equal(saves.length, 0);
    assert.equal(uiRenders.SettingsSavedStatus.at(-1)?.phase, "saving");
    await tick(t, 400);
    assert.equal(saves.length, 1);
    assert.equal(saves[0].microphone_device_id, "mic-1");
    assert.equal(uiRenders.SettingsSavedStatus.at(-1)?.phase, "idle");
    // Private storage only: the host config is never written.
    assert.equal(calls.some((call) => call.service === "config.save"), false);
  } finally { await view.cleanup(); }
});

test("a failed save shows its error with 重试, which writes the kept edit again", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let fail = true;
  const { view, saves } = await mountSettings({ set: async (value) => { if (fail) throw new Error("private write failed"); return value; } });
  try {
    await chooseSelectOption("麦克风", "USB 麦克风");
    await tick(t, 400);
    assert.match(text(), /private write failed/);
    fail = false;
    await act(async () => button("重试")!.click());
    assert.equal(saves.length, 2);
    assert.equal(saves[1].microphone_device_id, "mic-1");
    assert.doesNotMatch(text(), /private write failed/);
  } finally { await view.cleanup(); }
});

test("a failed read offers 重新加载 instead of waiting forever, and reloading shows the settings", async () => {
  let reads = 0;
  const { view, saves } = await mountSettings({ get: async () => { reads += 1; if (reads === 1) throw new Error("read failed"); return defaultVoicePreferences; } });
  try {
    assert.match(text(), /read failed/);
    assert.doesNotMatch(text(), /正在读取设置/);
    assert.equal(document.querySelector('input[aria-label="快捷键"]'), null);
    await act(async () => button("重新加载")!.click());
    await act(async () => { await Promise.resolve(); });
    assert.equal(reads, 2);
    assert.equal(document.querySelector<HTMLInputElement>('input[aria-label="快捷键"]')?.value, "Ctrl+Space");
    assert.doesNotMatch(text(), /read failed/);
    assert.equal(saves.length, 0, "a failed read never writes a default");
  } finally { await view.cleanup(); }
});

test("a failed microphone listing stays on the microphone row and blocks nothing else", async () => {
  const { view, uiRenders } = await mountSettings({ devices: async () => { throw new Error("audio device unavailable"); } });
  try {
    assert.match(text(), /麦克风列表读取失败：audio device unavailable/);
    assert.equal(uiRenders.InlineError.length, 0);
    assert.equal(combobox("麦克风").disabled, false);
    assert.equal(combobox("语音识别").disabled, false);
    assert.ok(document.querySelector('input[aria-label="快捷键"]'));
  } finally { await view.cleanup(); }
});

test("a kind with no installed provider is disabled with its status, and a saved one still shows as unavailable", async () => {
  const { view } = await mountSettings({ asr: [], tts: [], preferences: { tts: ttsRef } });
  try {
    assert.equal(combobox("语音识别").disabled, true);
    assert.equal(combobox("语音合成").disabled, true);
    assert.match(text(), /未安装语音识别插件/);
    assert.match(text(), /未安装语音合成插件/);
    assert.match(combobox("语音合成").textContent ?? "", /gpt_sovits_tts（不可用）/);
  } finally { await view.cleanup(); }
});

test("voice cannot be turned on until both providers are chosen, and once on a provider cannot be cleared", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { view, saves } = await mountSettings({ preferences: { asr: asrRef } });
  try {
    assert.equal(voiceSwitch().disabled, true);
    assert.match(text(), /需先选择语音识别与语音合成/);
    await act(async () => voiceSwitch().click());
    await tick(t, 400);
    assert.equal(saves.length, 0);

    await chooseSelectOption("语音合成", "GPT-SoVITS");
    assert.equal(voiceSwitch().disabled, false);
    assert.doesNotMatch(text(), /需先选择/);
    await act(async () => voiceSwitch().click());
    await tick(t, 400);
    assert.deepEqual(saves.at(-1), { ...defaultVoicePreferences, enabled: true, asr: asrRef, tts: ttsRef });

    const asrOptions = await optionLabels("语音识别");
    assert.ok(asrOptions.includes("SenseVoiceSmall"));
    assert.equal(asrOptions.includes("未选择"), false);
    assert.match(text(), /开启桌宠语音时必选/);
  } finally { await view.cleanup(); }
});

test("a valid hotkey is saved at once on Enter, without waiting for the quiet period", async () => {
  const { view, saves } = await mountSettings();
  try {
    const input = document.querySelector<HTMLInputElement>('input[aria-label="快捷键"]')!;
    await changeInputValue(input, "Alt+Space");
    assert.equal(saves.length, 0);
    await act(async () => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    await act(async () => { await Promise.resolve(); });
    assert.equal(saves.at(-1)?.hotkey, "Alt+Space");
  } finally { await view.cleanup(); }
});
