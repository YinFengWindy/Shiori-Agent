import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { defaultVoicePreferences } from "../background/voice/preferences";
let VoiceSettings: typeof import("./VoiceSettings").VoiceSettings;
before(async () => { const mounted = await mountTestComponent(null); ({ VoiceSettings } = await import("./VoiceSettings")); await mounted.cleanup(); });

test("private preference save failures retain the edited shortcut and never use host config", async () => {
  const { host, calls } = createFakeHostServices(); const requests: string[] = [];
  const client = createFakePluginClient({
    call: async <T,>(method: string) => { requests.push(method); if (method.endsWith(".set")) throw new Error("private write failed"); return defaultVoicePreferences as T; },
    services: { list: async () => ({ services: [] }), call: async <T,>() => undefined as T },
    background: { call: async <T,>() => [] as T },
  });
  const view = await mountTestComponent(<VoiceSettings client={client} host={host} subsectionId="desktop_pet" onSelectSubsection={() => {}} />);
  try {
    const input = view.container.querySelector("input")!;
    await changeInputValue(input, "Alt+Space");
    const save = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "保存")!;
    await act(async () => save.click());
    assert.equal(input.value, "Alt+Space"); assert.equal(save.disabled, false);
    assert.ok(requests.includes("voice.preferences.set")); assert.equal(calls.some((call) => call.service === "config.save"), false);
    assert.match(view.container.textContent ?? "", /private write failed/);
  } finally { await view.cleanup(); }
});

test("a failed private settings read does not create a saveable empty draft", async () => {
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({ call: async () => { throw new Error("read failed"); }, services: { list: async () => ({ services: [] }), call: async <T,>() => undefined as T }, background: { call: async <T,>() => [] as T } });
  const view = await mountTestComponent(<VoiceSettings client={client} host={host} subsectionId="desktop_pet" onSelectSubsection={() => {}} />);
  try { assert.match(view.container.textContent ?? "", /read failed/); assert.equal(view.container.querySelector("input"), null); }
  finally { await view.cleanup(); }
});

test("an invalid native accelerator remains a draft and never reaches private persistence", async () => {
  const { host } = createFakeHostServices(); const writes: string[] = [];
  const client = createFakePluginClient({
    call: async <T,>(method: string) => { if (method.endsWith(".set")) writes.push(method); return defaultVoicePreferences as T; },
    services: { list: async () => ({ services: [] }), call: async <T,>() => undefined as T },
    background: { call: async <T,>(method: string) => { if (method === "voice.preferences.validate") throw new Error("快捷键格式无效"); return [] as T; } },
  });
  const view = await mountTestComponent(<VoiceSettings client={client} host={host} subsectionId="desktop_pet" onSelectSubsection={() => {}} />);
  try {
    await changeInputValue(view.container.querySelector("input")!, "not-a-key");
    const save = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "保存")!;
    await act(async () => save.click());
    assert.equal(view.container.querySelector("input")!.value, "not-a-key"); assert.equal(save.disabled, false);
    assert.deepEqual(writes, []); assert.match(view.container.textContent ?? "", /快捷键格式无效/);
  } finally { await view.cleanup(); }
});
