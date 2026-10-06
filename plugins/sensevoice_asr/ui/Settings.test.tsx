import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { SenseVoiceSettingsPage } from "./Settings";

test("ASR settings save privately and retain a rejected URL draft", async () => {
  const { host, calls } = createFakeHostServices(); const requests: unknown[] = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "settings.set") throw new Error("invalid loopback URL");
    return { url: "http://127.0.0.1:8000", device: "cpu", model: "sensevoice" } as T;
  } });
  const view = await mountTestComponent(<SenseVoiceSettingsPage client={client} host={host} subsectionId="sensevoice_asr" onSelectSubsection={() => {}} />);
  try {
    await changeInputValue(view.container.querySelector("input")!, "https://remote.invalid");
    await act(async () => Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "保存")!.click());
    assert.equal(view.container.querySelector("input")?.value, "https://remote.invalid");
    assert.match(view.container.textContent ?? "", /invalid loopback URL/);
    assert.deepEqual(requests.at(-1), { method: "settings.set", payload: { url: "https://remote.invalid", device: "cpu", model: "sensevoice" } });
    assert.equal(calls.some((call) => call.service === "config.save"), false);
  } finally { await view.cleanup(); }
});

test("saving a new ASR endpoint clears the previous service health", async () => {
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "health") return { ready: true, model: "sensevoice", device: "cpu" } as T;
    if (method === "settings.set") return payload as T;
    return { url: "http://127.0.0.1:8000", device: "cpu", model: "sensevoice" } as T;
  } });
  const view = await mountTestComponent(<SenseVoiceSettingsPage client={client} host={host} subsectionId="sensevoice_asr" onSelectSubsection={() => {}} />);
  const button = (label: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label)!;
  try {
    await act(async () => button("检查连接").click());
    assert.match(view.container.textContent ?? "", /服务就绪/);
    await changeInputValue(view.container.querySelector("input")!, "http://127.0.0.1:8001");
    await act(async () => button("保存").click());
    assert.equal(view.container.querySelector("input")?.value, "http://127.0.0.1:8001");
    assert.equal(button("保存").disabled, true);
    assert.equal(view.container.querySelector('[role="status"]'), null);
  } finally { await view.cleanup(); }
});
