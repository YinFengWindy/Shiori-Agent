import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { GptSoVitsHealth } from "../shared/contracts";
import { useServiceHealth } from "./useServiceHealth";

test("saving new service settings invalidates the previous connection check", async () => {
  const pending = deferred<GptSoVitsHealth>();
  const client = createFakePluginClient({ call: async <T,>() => await pending.promise as T });
  let latest!: ReturnType<typeof useServiceHealth>;
  function Probe() { latest = useServiceHealth(client); return null; }
  const view = await mountTestComponent(<Probe />);
  try {
    let check!: Promise<void>;
    await act(async () => { check = latest.check(); });
    await act(async () => latest.clear());
    await act(async () => {
      pending.resolve({ reachable: true, configured_version: "v2ProPlus", model_verified: false, busy: false, recovery_required: true, instance: "old" });
      await check;
    });
    assert.equal(latest.health, null);
    assert.equal(latest.busy, false);
  } finally { await view.cleanup(); }
});
