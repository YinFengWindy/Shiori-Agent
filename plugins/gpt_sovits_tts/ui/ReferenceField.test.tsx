import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
let ReferenceField: typeof import("./ReferenceField").ReferenceField;
before(async () => { const view = await mountTestComponent(null); ({ ReferenceField } = await import("./ReferenceField")); await view.cleanup(); });

test("reference import uses owned asset identity and a role-scoped WAV picker without saving the role", async () => {
  const { host, calls } = createFakeHostServices({ pickFiles: async () => ["staged-reference.wav"] });
  const requests: unknown[] = []; const values: unknown[] = []; const busy: boolean[] = [];
  const client = createFakePluginClient({ call: async <T,>(name: string, payload?: Record<string, unknown>) => { requests.push({ name, payload }); return { asset: "owned.wav", duration: 4.2 } as T; } });
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><ReferenceField title="开心" roleId="role" client={client} value={null} disabled={false} onChange={(value) => values.push(value)} onBusyChange={(value) => busy.push(value)} /></PluginHostServicesProvider>);
  try {
    await act(async () => view.container.querySelector("button")!.click());
    assert.deepEqual(requests, [{ name: "reference.import", payload: { role_id: "role", source: "staged-reference.wav" } }]);
    assert.deepEqual(values, [{ asset: "owned.wav", prompt_text: "", prompt_lang: "zh" }]);
    assert.deepEqual(busy, [true, false]);
    assert.deepEqual(calls.find((call) => call.service === "pickFiles"), { service: "pickFiles", options: { namespace: "gpt_sovits_tts-audio", filters: [{ name: "WAV 参考音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 } });
  } finally { await view.cleanup(); }
});
