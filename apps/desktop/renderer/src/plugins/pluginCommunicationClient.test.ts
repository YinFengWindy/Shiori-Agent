import assert from "node:assert/strict";
import { test } from "node:test";
import type { BridgeEvent } from "../../../src/bridge/shared";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { createPluginCommunicationClient } from "./pluginCommunicationClient";

function host() {
  const listeners = new Set<(event: BridgeEvent) => void>();
  const calls: Parameters<DesktopInvoke>[0][] = [];
  let failOpen = false;
  const invoke: DesktopInvoke = async (request) => {
    calls.push(request);
    const error = request.method.endsWith(".open") && failOpen
      ? { code: "runtime_reloading", message: "retry after reload" }
      : request.payload.target === "undeclared"
        ? { code: "plugin_dependency_undeclared", message: "undeclared" } : null;
    return { id: "test", type: "response", method: request.method, error,
      payload: request.method.endsWith(".open") ? { generation: "g1" }
        : request.method.endsWith(".resolve") ? { available: request.payload.target !== "missing" }
          : request.method.endsWith(".call") ? { result: "done" } : { ok: true } };
  };
  return {
    calls, listeners,
    failOpen: (value: boolean) => { failOpen = value; },
    emit: (method: string, payload: Record<string, unknown> = {}, generation = "g1") => {
      for (const listener of [...listeners]) listener({ id: "event", type: "event", method, payload, pluginGeneration: generation });
    },
    options: { invoke, onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; } },
  };
}

test("own and declared peer calls/events share local names and isolate namespaces", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", fixture.options);
  const heard: string[] = [];
  await client.events.on("changed", () => heard.push("own"));
  const peer = await client.dependency("provider");
  assert.ok(peer);
  await peer.events.on("changed", () => heard.push("peer"));
  fixture.emit("plugin.demo.changed");
  fixture.emit("plugin.provider.changed");
  fixture.emit("plugin.stranger.changed");
  fixture.emit("changed");
  fixture.emit("plugin.provider.changed", {}, "old");
  assert.deepEqual(heard, ["own", "peer"]);
  await peer.call("read", { x: 1 });
  assert.deepEqual(fixture.calls.at(-1), { method: "plugin.provider.read", payload: { x: 1, __plugin_context: { plugin_id: "demo", generation: "g1" } } });
  assert.equal(await peer.background.call("sync"), "done");
  await assert.rejects(client.call("plugin.provider.read"), { code: "plugin_invalid_name" });
  await client.dispose();
  assert.equal(fixture.listeners.size, 0);
});

test("missing peers are nullable, undeclared peers fail explicitly, retained peers cannot cross generations", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", fixture.options);
  assert.equal(await client.dependency("missing"), null);
  await assert.rejects(client.dependency("undeclared"), { code: "plugin_dependency_undeclared" });
  const peer = await client.dependency("provider");
  fixture.emit("runtime.applied");
  await assert.rejects(peer!.call("read"), { code: "plugin_unavailable" });
  assert.equal(fixture.listeners.size, 0);
});

test("an explicit retry can recover from a transient open failure", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", fixture.options);
  fixture.failOpen(true);
  await assert.rejects(client.call("read"), { code: "runtime_reloading" });
  fixture.failOpen(false);
  assert.deepEqual(await client.call("read"), { ok: true });
  await client.dispose();
});

test("a no-op runtime notification keeps subscriptions and pending context alive", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", fixture.options);
  let heard = 0;
  await client.events.on("changed", () => { heard += 1; });
  fixture.emit("runtime.applied", { changed: false });
  fixture.emit("plugin.demo.changed");
  assert.equal(heard, 1);
  assert.deepEqual(await client.call("read"), { ok: true });
  await client.dispose();
});

test("unmount while open is pending rejects the caller and closes its late context", async () => {
  const fixture = host();
  let complete!: () => void;
  const gate = new Promise<void>((resolve) => { complete = resolve; });
  const client = createPluginCommunicationClient("demo", { ...fixture.options, invoke: async (request) => {
    if (request.method.endsWith(".open")) await gate;
    return fixture.options.invoke(request);
  } });
  const pending = client.call("read");
  const disposed = client.dispose();
  await assert.rejects(pending, { code: "plugin_unavailable" });
  complete();
  await disposed;
  assert.equal(fixture.calls.at(-1)?.method, "plugins.communication.close");
  assert.equal(fixture.listeners.size, 0);
});

test("publication closes an in-flight handshake even when it returns the successor's token", async () => {
  const fixture = host();
  let complete!: () => void;
  const gate = new Promise<void>((resolve) => { complete = resolve; });
  const client = createPluginCommunicationClient("demo", { ...fixture.options, invoke: async (request) => {
    if (request.method.endsWith(".open")) {
      await gate;
      return { id: "open", type: "response", method: request.method, error: null, payload: { generation: "successor" } };
    }
    return fixture.options.invoke(request);
  } });
  const pending = client.call("read");
  fixture.emit("runtime.applied", { changed: true });
  await assert.rejects(pending, { code: "plugin_unavailable" });
  complete();
  await client.dispose();
  assert.equal(fixture.calls.at(-1)?.method, "plugins.communication.close");
  assert.equal(fixture.calls.at(-1)?.payload.generation, "successor");
});

test("bridge exit releases local subscriptions without restarting transport for cleanup", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", fixture.options);
  await client.events.on("changed", () => {});
  const count = fixture.calls.length;
  fixture.emit("bridge.exit");
  await client.dispose();
  assert.equal(fixture.calls.length, count);
  assert.equal(fixture.listeners.size, 0);
});

test("background handler failures are returned to the exact request and disposal removes registration", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", { ...fixture.options, background: true });
  await client.handle("sync", async () => { throw new Error("binding failed"); });
  const owner = fixture.calls[0].payload.owner;
  fixture.emit("plugin.demo.__request", { owner: "another", name: "sync", request_id: "wrong" });
  fixture.emit("plugin.demo.__request", { owner, name: "sync", request_id: "right" });
  await new Promise((resolve) => setImmediate(resolve));
  const replies = fixture.calls.filter((call) => call.method.endsWith(".reply"));
  assert.equal(replies.length, 1);
  assert.equal(replies[0].payload.request_id, "right");
  assert.deepEqual(replies[0].payload.error, { code: "plugin_handler_failed", message: "binding failed" });
  await client.dispose();
  assert.equal(fixture.calls.at(-1)?.method, "plugins.communication.close");
});
