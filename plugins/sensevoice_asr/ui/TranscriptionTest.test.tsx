import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TranscriptionTest } from "./TranscriptionTest";

test("file transcription uses an independent WAV picker and the provider's bounded request timeout", async () => {
  const { host, calls } = createFakeHostServices({ pickFiles: async () => ["staged.wav"] });
  const requests: unknown[] = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>, options?: { timeoutMs?: number }) => {
    requests.push({ method, payload, options }); return { text: "你好，角色名。" } as T;
  } });
  const view = await mountTestComponent(<TranscriptionTest client={client} host={host} />);
  try {
    await act(async () => view.container.querySelector("button")!.click());
    assert.deepEqual(requests, [{ method: "transcribe_file", payload: { source: "staged.wav" }, options: { timeoutMs: 65_000 } }]);
    assert.deepEqual(calls.find((call) => call.service === "pickFiles"), { service: "pickFiles", options: { namespace: "sensevoice_asr-audio", filters: [{ name: "WAV 音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 } });
    assert.equal(view.container.querySelector("textarea")?.value, "你好，角色名。");
  } finally { await view.cleanup(); }
});

test("picker cancellation sends nothing and failed transcription keeps the previous result", async () => {
  let selected = false; let fail = false; let requests = 0;
  const { host } = createFakeHostServices({ pickFiles: async () => selected ? ["sample.wav"] : [] });
  const client = createFakePluginClient({ call: async <T,>() => { requests++; if (fail) throw new Error("model unavailable"); return { text: "已识别" } as T; } });
  const view = await mountTestComponent(<TranscriptionTest client={client} host={host} />);
  try {
    const click = () => act(async () => view.container.querySelector("button")!.click());
    await click(); assert.equal(requests, 0);
    selected = true; await click(); fail = true; await click();
    assert.equal(view.container.querySelector("textarea")?.value, "已识别");
    assert.match(view.container.textContent ?? "", /model unavailable/);
    assert.equal(view.container.querySelector("button")?.disabled, false);
  } finally { await view.cleanup(); }
});
