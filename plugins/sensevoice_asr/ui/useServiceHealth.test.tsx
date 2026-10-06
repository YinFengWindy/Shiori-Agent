import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { SenseVoiceHealth, SenseVoiceSettings } from "./contract";
import { useServiceHealth } from "./useServiceHealth";

test("endpoint changes invalidate a pending check and service errors remain visible", async () => {
  const pending = deferred<SenseVoiceHealth>();
  let failure = false;
  const client = createFakePluginClient({ call: async <T,>() => {
    if (failure) throw { message: "TypeError: CPU model missing" };
    return await pending.promise as T;
  } });
  const first = { connection_mode: "external", url: "http://127.0.0.1:8000", device: "cpu", model: "sensevoice" } satisfies SenseVoiceSettings;
  const second = { ...first, url: "http://127.0.0.1:8001" };
  let latest!: ReturnType<typeof useServiceHealth>;
  function Probe({ settings }: { settings: SenseVoiceSettings | null }) { latest = useServiceHealth(client, settings); return null; }
  const view = await mountTestComponent(<Probe settings={first} />);
  try {
    let check!: Promise<void>;
    await act(async () => { check = latest.check(); });
    await view.render(<Probe settings={second} />);
    await act(async () => { pending.resolve({ ready: true, model: "sensevoice", device: "cpu" }); await check; });
    assert.equal(latest.health, null); assert.equal(latest.busy, false);
    failure = true;
    await act(async () => latest.check());
    assert.equal(latest.error, "CPU model missing");
    await view.render(<Probe settings={null} />);
    await act(async () => latest.check());
    assert.equal(latest.error, "");
  } finally { await view.cleanup(); }
});
