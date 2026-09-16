import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import type { WebContents } from "electron";
import type { DesktopBridgeClient } from "../bridge/bridgeClient.js";
import { createPluginCommunicationLifecycle } from "./communicationLifecycle.js";

test("document identity is host-attributed and crash or close reclaims its contexts", async () => {
  const calls: unknown[] = [];
  const bridge = { isRunning: () => true, invoke: async (request: unknown) => { calls.push(request); return {}; } } as unknown as DesktopBridgeClient;
  const sender = Object.assign(new EventEmitter(), { id: 17 });
  const attribute = createPluginCommunicationLifecycle(bridge);
  const request = { method: "plugins.communication.open", payload: { owner: "context", renderer: "spoof" } };
  const first = await attribute(sender as unknown as WebContents, request);
  assert.notEqual(first.payload.renderer, "spoof");
  assert.equal((await attribute(sender as unknown as WebContents, request)).payload.renderer, first.payload.renderer);
  assert.equal(sender.listenerCount("destroyed"), 1);
  sender.emit("render-process-gone");
  const recovered = await attribute(sender as unknown as WebContents, request);
  assert.notEqual(recovered.payload.renderer, first.payload.renderer);
  assert.deepEqual(calls, [{ method: "plugins.communication.disconnect", payload: { renderer: first.payload.renderer } }]);
  sender.emit("destroyed");
  await Promise.resolve();
  assert.deepEqual(calls.at(-1), { method: "plugins.communication.disconnect", payload: { renderer: recovered.payload.renderer } });
  assert.equal(sender.listenerCount("did-start-navigation"), 0);
  assert.equal(sender.listenerCount("render-process-gone"), 0);
});

test("same-document and subframe navigation preserve communication owners", async () => {
  const bridge = { invoke: () => assert.fail("unrelated navigation must not disconnect") } as unknown as DesktopBridgeClient;
  const sender = Object.assign(new EventEmitter(), { id: 17 });
  const attribute = createPluginCommunicationLifecycle(bridge);
  const request = { method: "plugins.communication.open", payload: { owner: "context" } };
  const first = await attribute(sender as unknown as WebContents, request);
  sender.emit("did-start-navigation", { isMainFrame: true, isSameDocument: true });
  sender.emit("did-start-navigation", { isMainFrame: false, isSameDocument: false });
  assert.equal((await attribute(sender as unknown as WebContents, request)).payload.renderer, first.payload.renderer);
});

test("reload awaits old document cleanup and scopes delayed cleanup away from its successor", async () => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const calls: unknown[] = [];
  const bridge = { isRunning: () => true, invoke: async (request: unknown) => { calls.push(request); await pending; return {}; } } as unknown as DesktopBridgeClient;
  const sender = Object.assign(new EventEmitter(), { id: 17 });
  const attribute = createPluginCommunicationLifecycle(bridge);
  const request = { method: "plugins.communication.open", payload: { owner: "context" } };
  const first = await attribute(sender as unknown as WebContents, request);
  sender.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  let successorOpened = false;
  const successor = attribute(sender as unknown as WebContents, request).then((value) => { successorOpened = true; return value; });
  await Promise.resolve();
  assert.equal(successorOpened, false);
  assert.deepEqual(calls, [{ method: "plugins.communication.disconnect", payload: { renderer: first.payload.renderer } }]);
  release();
  const second = await successor;
  assert.notEqual(second.payload.renderer, first.payload.renderer);
  sender.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  const third = await attribute(sender as unknown as WebContents, request);
  assert.notEqual(third.payload.renderer, second.payload.renderer);
  assert.deepEqual(calls.at(-1), { method: "plugins.communication.disconnect", payload: { renderer: second.payload.renderer } });
});

test("an open waiting through another document replacement never registers", async () => {
  const bridge = { isRunning: () => true, invoke: async () => ({}) } as unknown as DesktopBridgeClient;
  const sender = Object.assign(new EventEmitter(), { id: 17 });
  const attribute = createPluginCommunicationLifecycle(bridge);
  const request = { method: "plugins.communication.open", payload: {} };
  await attribute(sender as unknown as WebContents, request);
  sender.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  const departed = attribute(sender as unknown as WebContents, request);
  sender.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  await assert.rejects(departed, /document was replaced/);
  await attribute(sender as unknown as WebContents, request);
});
