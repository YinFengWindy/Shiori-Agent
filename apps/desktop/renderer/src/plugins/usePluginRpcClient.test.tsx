import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { PluginRpcClient } from "./pluginBridgeClient";
import { usePluginRpcClient } from "./usePluginRpcClient";

test("mounted contributions renew client subscriptions on real generation changes and release them on unmount", async () => {
  const listeners = new Set<(event: BridgeEvent) => void>();
  const clients: PluginRpcClient[] = [];
  let token = "g1";
  let received = 0;
  function Contribution() {
    const client = usePluginRpcClient("demo");
    useEffect(() => {
      clients.push(client);
      let off: (() => void) | undefined;
      void client.events.on("changed", () => { received += 1; }).then((unsubscribe) => { off = unsubscribe; });
      return () => off?.();
    }, [client]);
    return null;
  }
  const view = await mountTestComponent(<Contribution />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    invoke: async ({ method }: { method: string }) => ({ id: "response", type: "response", method, error: null,
      payload: method.endsWith(".open") ? { generation: token } : { available: true } }),
  } } });
  const emit = (method: string, payload = {}) => {
    for (const listener of [...listeners]) listener({ id: "event", type: "event", method, payload, pluginGeneration: token });
  };
  try {
    await act(async () => { emit("plugin.demo.changed"); emit("runtime.applied", { changed: false }); });
    assert.equal(clients.length, 1);
    token = "g2";
    await act(async () => { emit("runtime.applied", { changed: true }); });
    assert.equal(clients.length, 2);
    await assert.rejects(clients[0].call("read"), { code: "plugin_unavailable" });
    emit("plugin.demo.changed");
    assert.equal(received, 2);
    await act(async () => { emit("bridge.exit"); });
    assert.equal(clients.length, 2, "exit cannot start a client that implicitly reconnects");
    token = "g3";
    await act(async () => { emit("bridge.ready"); });
    assert.equal(clients.length, 3);
  } finally { await view.cleanup(); }
  assert.equal(listeners.size, 0);
});
