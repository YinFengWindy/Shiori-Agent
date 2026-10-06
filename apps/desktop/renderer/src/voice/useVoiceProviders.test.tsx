import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { BridgeResponse, VoiceProviderDescriptor } from "../../../src/bridge/shared";
import { useVoiceProviders } from "./useVoiceProviders";

const provider: VoiceProviderDescriptor = { id: "test", label: "Test", kind: "tts", plugin_id: "test", available: true, capabilities: { emotions: ["bright"], voice_cloning: false } };
function response(providers: VoiceProviderDescriptor[]): BridgeResponse {
  return { id: "r", type: "response", method: "voice.providers", payload: { providers }, error: null };
}

describe("useVoiceProviders", () => {
  it("refreshes plugin availability and ignores a stale response after bridge exit", async () => {
    const listeners = new Set<(event: BridgeEvent) => void>();
    const requests: Array<(response: BridgeResponse) => void> = [];
    let latest: ReturnType<typeof useVoiceProviders> | undefined;
    function Probe() {
      const value = useVoiceProviders();
      useEffect(() => { latest = value; });
      return null;
    }
    const view = await mountTestComponent(<Probe />, { windowGlobals: { miraDesktop: {
      invoke: ({ method }: { method: string }) => {
        assert.equal(method, "voice.providers");
        return new Promise<BridgeResponse>((resolve) => requests.push(resolve));
      },
      onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    } } });
    const emit = (method: string) => { for (const listener of listeners) listener({ id: "e", type: "event", method, payload: {} }); };
    try {
      await act(async () => requests[0](response([provider])));
      assert.equal(latest?.providers[0].available, true);
      await act(async () => emit("plugins.changed"));
      await act(async () => requests[1](response([{ ...provider, available: false }])));
      assert.equal(latest?.providers[0].available, false);
      await act(async () => emit("runtime.applied"));
      await act(async () => emit("bridge.exit"));
      assert.equal(requests.length, 3, "bridge exit must not trigger another discovery request");
      await act(async () => requests[2](response([provider])));
      assert.equal(latest?.providers.length, 0);
      assert.match(latest?.error ?? "", /不可用/);
      await act(async () => emit("bridge.ready"));
      await act(async () => requests[3](response([provider])));
      assert.equal(latest?.providers[0].available, true);
      assert.equal(latest?.error, "");
    } finally { await view.cleanup(); }
    assert.equal(listeners.size, 0);
  });

  it("surfaces discovery errors without keeping a usable provider", async () => {
    let latest: ReturnType<typeof useVoiceProviders> | undefined;
    function Probe() {
      const value = useVoiceProviders();
      useEffect(() => { latest = value; });
      return null;
    }
    const view = await mountTestComponent(<Probe />, { windowGlobals: { miraDesktop: {
      invoke: async () => ({ ...response([]), error: { code: "offline", message: "backend offline" } }),
      onEvent: () => () => undefined,
    } } });
    try {
      assert.deepEqual(latest?.providers, []);
      assert.equal(latest?.loading, false);
      assert.match(latest?.error ?? "", /backend offline/);
    } finally { await view.cleanup(); }
  });
});
