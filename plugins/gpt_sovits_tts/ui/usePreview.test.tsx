import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { TtsResult } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { usePreview } from "./usePreview";

test("long preview synthesis uses the public service and only hands current audio to its own background", async (context) => {
  const inference = deferred<TtsResult>(); const calls: unknown[] = [];
  const client = createFakePluginClient({
    services: { list: async () => ({ services: [] }), call: async <T,>(service: unknown, name: string, payload?: Record<string, unknown>) => { calls.push({ service, name, payload }); return await inference.promise as T; } },
    background: { call: async <T,>(name: string, payload?: Record<string, unknown>) => { calls.push({ name, payload }); return { id: payload?.id, role_id: "role", phase: "playing", error: "" } as T; } },
  });
  let latest!: ReturnType<typeof usePreview>;
  function Probe() { latest = usePreview(client, "role"); return null; }
  const view = await mountTestComponent(<Probe />);
  context.mock.timers.enable({ apis: ["setTimeout"] });
  try {
    let pending!: Promise<void>;
    await act(async () => { pending = latest.start("你好", "开心"); });
    await act(async () => context.mock.timers.tick(120_000));
    assert.equal(latest.state.phase, "generating"); assert.equal(calls.length, 1);
    assert.deepEqual(calls[0], { service: { plugin_id: "gpt_sovits_tts", service_id: "tts" }, name: "synthesize", payload: { role_id: "role", text: "你好", mood: "开心" } });
    await act(async () => { inference.resolve({ audio_base64: "actual-audio", format: "wav" }); await pending; });
    assert.equal(latest.state.phase, "playing");
    assert.deepEqual(calls[1], { name: "preview.play", payload: { id: latest.state.id, role_id: "role", audio_base64: "actual-audio", format: "wav" } });
  } finally { await view.cleanup(); }
});

for (const retire of ["stop", "role", "unmount"] as const) {
  test(`${retire} during synthesis prevents a late result from reaching background playback`, async () => {
    const inference = deferred<TtsResult>(); const commands: string[] = [];
    const client = createFakePluginClient({
      services: { list: async () => ({ services: [] }), call: async <T,>() => await inference.promise as T },
      background: { call: async <T,>(name: string) => { commands.push(name); return {} as T; } },
    });
    let latest!: ReturnType<typeof usePreview>;
    function Probe({ role }: { role: string }) { latest = usePreview(client, role); return null; }
    const view = await mountTestComponent(<Probe role="one" />);
    let cleaned = false;
    try {
      let pending!: Promise<void>;
      await act(async () => { pending = latest.start("旧声音", ""); });
      if (retire === "stop") await act(async () => latest.stop());
      else if (retire === "role") await view.render(<Probe role="two" />);
      else { await view.cleanup(); cleaned = true; }
      await act(async () => { inference.resolve({ audio_base64: "late", format: "wav" }); await pending; });
      assert.equal(commands.includes("preview.play"), false);
    } finally { if (!cleaned) await view.cleanup(); }
  });
}

test("public provider failures stay visible and never submit audio to the background", async () => {
  const commands: string[] = [];
  const client = createFakePluginClient({
    services: { list: async () => ({ services: [] }), call: async () => { throw new Error("inference requires service restart"); } },
    background: { call: async <T,>(name: string) => { commands.push(name); return {} as T; } },
  });
  let latest!: ReturnType<typeof usePreview>;
  function Probe() { latest = usePreview(client, "role"); return null; }
  const view = await mountTestComponent(<Probe />);
  try {
    await act(async () => latest.start("你好", ""));
    assert.equal(latest.busy, false);
    assert.match(latest.state.error, /inference requires service restart/);
    assert.deepEqual(commands, []);
  } finally { await view.cleanup(); }
});
