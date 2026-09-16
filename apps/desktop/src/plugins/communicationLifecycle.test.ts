import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import type { WebContents } from "electron";
import type { DesktopBridgeClient } from "../bridge/bridgeClient.js";
import { createPluginCommunicationLifecycle } from "./communicationLifecycle.js";

test("renderer identity is host-attributed and crash or close reclaims its contexts", async () => {
  const calls: unknown[] = [];
  const bridge = { isRunning: () => true, invoke: async (request: unknown) => { calls.push(request); return {}; } } as unknown as DesktopBridgeClient;
  const sender = Object.assign(new EventEmitter(), { id: 17 });
  const attribute = createPluginCommunicationLifecycle(bridge);
  const request = { method: "plugins.communication.open", payload: { owner: "context", renderer: "spoof" } };
  assert.equal(attribute(sender as unknown as WebContents, request).payload.renderer, "17");
  attribute(sender as unknown as WebContents, request);
  assert.equal(sender.listenerCount("destroyed"), 1);
  sender.emit("render-process-gone");
  await Promise.resolve();
  assert.deepEqual(calls, [{ method: "plugins.communication.disconnect", payload: { renderer: "17" } }]);
});
