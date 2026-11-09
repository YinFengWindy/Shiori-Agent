import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { TtsResult } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { usePreview } from "./usePreview";

test("stop during synthesis cannot hand a late result to native playback", async () => {
  const synthesis = deferred<TtsResult>();
  const commands: string[] = [];
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({
    services: { list: async () => ({ services: [] }), call: async <T,>() => await synthesis.promise as T },
    background: { call: async <T,>(method: string) => { commands.push(method); return {} as T; } },
  });
  let latest!: ReturnType<typeof usePreview>;
  function Probe() { latest = usePreview(client, "alice", host.feedback); return null; }
  const view = await mountTestComponent(<Probe />);
  try {
    let pending!: Promise<void>;
    await act(async () => { pending = latest.start("hello"); });
    await act(async () => latest.stop());
    await act(async () => { synthesis.resolve({ audio_base64: "late", format: "mp3" }); await pending; });
    assert.equal(commands.includes("preview.play"), false);
    assert.equal(latest.state.phase, "idle");
  } finally { await view.cleanup(); }
});

test("changing roles invalidates pending synthesis from the previous role", async () => {
  const synthesis = deferred<TtsResult>();
  const commands: string[] = [];
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({
    services: { list: async () => ({ services: [] }), call: async <T,>() => await synthesis.promise as T },
    background: { call: async <T,>(method: string) => { commands.push(method); return {} as T; } },
  });
  let latest!: ReturnType<typeof usePreview>;
  function Probe({ role }: { role: string }) { latest = usePreview(client, role, host.feedback); return null; }
  const view = await mountTestComponent(<Probe role="alice" />);
  try {
    let pending!: Promise<void>;
    await act(async () => { pending = latest.start("hello"); });
    await view.render(<Probe role="bob" />);
    await act(async () => { synthesis.resolve({ audio_base64: "late", format: "mp3" }); await pending; });
    assert.equal(commands.includes("preview.play"), false);
  } finally { await view.cleanup(); }
});
