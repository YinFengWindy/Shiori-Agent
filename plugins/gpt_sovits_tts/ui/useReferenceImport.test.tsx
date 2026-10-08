import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useReferenceImport } from "./useReferenceImport";

async function probe(pickFiles: () => Promise<string[]>, call: (method: string, payload?: Record<string, unknown>) => Promise<unknown>) {
  const fake = createFakeHostServices({ pickFiles });
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => await call(method, payload) as T });
  let latest!: ReturnType<typeof useReferenceImport>;
  function Probe() { latest = useReferenceImport(client, "role"); return null; }
  const view = await mountTestComponent(<PluginHostServicesProvider services={fake.host}><Probe /></PluginHostServicesProvider>);
  return { ...fake, view, latest: () => latest };
}

test("a picked WAV is imported through the role-scoped picker while the mood is busy", async () => {
  const requests: unknown[] = []; const done = deferred<unknown>();
  const ui = await probe(async () => ["clip.wav"], (method, payload) => { requests.push({ method, payload }); return done.promise; });
  try {
    let result!: Promise<unknown>;
    await act(async () => { result = ui.latest().importFor("开心"); });
    assert.equal(ui.latest().busy, "开心");
    assert.deepEqual(ui.calls.find((call) => call.service === "pickFiles"), { service: "pickFiles", options: { namespace: "gpt_sovits_tts-audio", filters: [{ name: "WAV 参考音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 } });
    await act(async () => { done.resolve({ asset: "owned.wav", duration: 4.2 }); await result; });
    assert.deepEqual(await result, { asset: "owned.wav", duration: 4.2 });
    assert.deepEqual(requests, [{ method: "reference.import", payload: { role_id: "role", source: "clip.wav" } }]);
    assert.equal(ui.latest().busy, null);
  } finally { await ui.view.cleanup(); }
});

test("a cancelled picker imports nothing and a failed import is reported", async () => {
  let picked: string[] = []; const requests: string[] = [];
  const ui = await probe(async () => picked, async (method) => { requests.push(method); throw new Error("参考音频必须为 3–10 秒 PCM WAV"); });
  try {
    let result: unknown;
    await act(async () => { result = await ui.latest().importFor(""); });
    assert.equal(result, null);
    assert.deepEqual(requests, []);
    picked = ["long.wav"];
    await act(async () => { result = await ui.latest().importFor(""); });
    assert.equal(result, null);
    assert.equal(ui.latest().error, "参考音频必须为 3–10 秒 PCM WAV");
    assert.equal(ui.latest().busy, null);
  } finally { await ui.view.cleanup(); }
});
