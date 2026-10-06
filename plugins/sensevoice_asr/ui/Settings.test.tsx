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
