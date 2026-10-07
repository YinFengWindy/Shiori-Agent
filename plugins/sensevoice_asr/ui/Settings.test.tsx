import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, chooseSelectOption, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { SenseVoiceSettingsPage } from "./Settings";
import type { SenseVoiceSettings } from "./contract";

const settings = { connection_mode: "external", url: "http://127.0.0.1:8000", device: "cpu", model: "sensevoice" } satisfies SenseVoiceSettings;

function buttons(container: HTMLElement) {
  return (label: string) => Array.from(container.querySelectorAll("button")).find((item) => item.textContent === label);
}

test("ASR settings autosave privately; a rejected URL stays in the draft until retry, and a failed read offers reload", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { host, calls } = createFakeHostServices(); const requests: unknown[] = [];
  let failLoad = true; let failSave = true;
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "settings.get") { if (failLoad) throw new Error("settings unreadable"); return settings as T; }
    if (failSave) throw new Error("invalid loopback URL");
    return payload as T;
  } });
  const view = await mountTestComponent(<SenseVoiceSettingsPage client={client} host={host} subsectionId="sensevoice_asr" onSelectSubsection={() => {}} />);
  const button = buttons(view.container);
  try {
    assert.match(view.container.textContent ?? "", /settings unreadable/);
    failLoad = false;
    await act(async () => button("重新加载")!.click());
    assert.equal(button("保存"), undefined);

    const url = view.container.querySelector<HTMLInputElement>('[aria-label="服务地址"]')!;
    await changeInputValue(url, "https://remote.invalid");
    await act(async () => t.mock.timers.tick(400));
    assert.equal(url.value, "https://remote.invalid");
    assert.match(view.container.textContent ?? "", /invalid loopback URL/);
    assert.equal(button("检查连接")!.disabled, true);
    assert.deepEqual(requests.at(-1), { method: "settings.set", payload: { ...settings, url: "https://remote.invalid" } });

    failSave = false;
    await act(async () => button("重试")!.click());
    assert.equal(button("重试"), undefined);
    assert.equal(button("检查连接")!.disabled, false);
    assert.equal(calls.some((call) => call.service === "config.save"), false);
  } finally { await view.cleanup(); }
});

test("saving a new ASR endpoint clears the previous service health", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "health") return { ready: true, model: "sensevoice", device: "cpu" } as T;
    if (method === "settings.set") return payload as T;
    return settings as T;
  } });
  const view = await mountTestComponent(<SenseVoiceSettingsPage client={client} host={host} subsectionId="sensevoice_asr" onSelectSubsection={() => {}} />);
  try {
    await act(async () => buttons(view.container)("检查连接")!.click());
    assert.match(view.container.textContent ?? "", /服务就绪/);
    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="服务地址"]')!, "http://127.0.0.1:8001");
    await act(async () => t.mock.timers.tick(400));
    assert.equal(view.container.querySelector<HTMLInputElement>('[aria-label="服务地址"]')?.value, "http://127.0.0.1:8001");
    assert.doesNotMatch(view.container.textContent ?? "", /服务就绪/);
  } finally { await view.cleanup(); }
});

test("managed runtime actions wait until a mode change is stored", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { host } = createFakeHostServices(); const write = deferred<SenseVoiceSettings>();
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    if (method === "settings.get") return settings as T;
    if (method === "settings.set") return write.promise as Promise<T>;
    return { phase: "stopped", revision: "r1", busy: false, installed: false, running: false, received: 0, total: 0, item: "", error: "", reclaimable: 0, staging: false, location: "C:/runtime", required: 0, free: 0, relocatable: true } as T;
  } });
  const view = await mountTestComponent(<SenseVoiceSettingsPage client={client} host={host} subsectionId="sensevoice_asr" onSelectSubsection={() => {}} />);
  const button = buttons(view.container);
  try {
    await chooseSelectOption("连接模式", "插件托管");
    assert.equal(button("下载环境")!.disabled, true);
    await act(async () => t.mock.timers.tick(400));
    assert.equal(button("下载环境")!.disabled, true);
    await act(async () => write.resolve({ ...settings, connection_mode: "managed" }));
    assert.equal(button("下载环境")!.disabled, false);
  } finally { await view.cleanup(); }
});
