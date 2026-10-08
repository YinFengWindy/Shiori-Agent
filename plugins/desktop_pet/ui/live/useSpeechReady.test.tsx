import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useSpeechReady } from "./useSpeechReady";

function Probe({ client, open, onRender }: { client: PluginRpcClient; open: boolean; onRender(state: ReturnType<typeof useSpeechReady>): void }) {
  onRender(useSpeechReady(client, open));
  return null;
}

test("speech needs voice on and a TTS provider, is re-read on each open, and a failed read stays unknown", async () => {
  const answers: Array<() => Promise<unknown>> = [
    async () => ({ enabled: true, tts: null }),
    async () => ({ enabled: true, tts: { plugin_id: "tts", service_id: "say" } }),
    async () => { throw new Error("读取失败"); },
  ];
  let reads = 0;
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    assert.equal(method, "voice.preferences.get");
    return await answers[reads++]() as T;
  } });
  let state: ReturnType<typeof useSpeechReady> | null = null;
  const render = (open: boolean) => <Probe client={client} open={open} onRender={(next) => { state = next; }} />;
  const view = await mountTestComponent(render(true));
  try {
    assert.deepEqual(state, { ready: false, error: "" });
    await view.render(render(false));
    assert.equal(reads, 1, "a closed dialog reads nothing");
    await view.render(render(true));
    assert.deepEqual(state, { ready: true, error: "" });
    await view.render(render(false));
    await view.render(render(true));
    assert.deepEqual(state, { ready: null, error: "读取失败" });
  } finally { await view.cleanup(); }
});
