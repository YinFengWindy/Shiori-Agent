import assert from "node:assert/strict";
import { test } from "node:test";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
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

test("public services use the active owner context without a static dependency lookup", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("consumer", fixture.options);
  await client.services.list("shiori.asr.v1");
  const request = fixture.calls.at(-1)!;
  assert.equal(request.method, "plugins.communication.services.list");
  assert.equal(request.payload.contract, "shiori.asr.v1");
  assert.equal(request.timeoutMs, 20_000);
  assert.equal(request.payload.plugin_id, "consumer");
  assert.equal(request.payload.generation, "g1");
  assert.equal(typeof request.payload.owner, "string");
  await client.services.call({ plugin_id: "new-provider", service_id: "asr" }, "transcribe", { audio_base64: "AQ==", format: "wav" });
  assert.equal(fixture.calls.at(-1)?.method, "plugins.communication.services.call");
  assert.equal(fixture.calls.at(-1)?.timeoutMs, undefined);
  assert.deepEqual(fixture.calls.at(-1)?.payload.service, { plugin_id: "new-provider", service_id: "asr" });
  assert.equal(fixture.calls.some((item) => item.method.endsWith(".resolve")), false);
  fixture.emit("runtime.applied");
  await assert.rejects(client.services.list("shiori.asr.v1"));
});

for (const end of ["dispose", "bridge.exit"] as const) {
  test(`a pending public service stops delivering when its context ends through ${end}`, async () => {
    const fixture = host();
    let complete!: () => void;
    const gate = new Promise<void>((resolve) => { complete = resolve; });
    const client = createPluginCommunicationClient("consumer", { ...fixture.options, invoke: async (request) => {
      if (request.method === "plugins.communication.services.call") await gate;
      return fixture.options.invoke(request);
    } });
    let delivered = false;
    const pending = client.services.call({ plugin_id: "neutral", service_id: "slow" }, "run").then((result) => { delivered = true; return result; });
    await new Promise<void>((resolve) => setImmediate(resolve));
    if (end === "dispose") await client.dispose();
    else fixture.emit("bridge.exit");
    await assert.rejects(pending, { code: "plugin_unavailable" });
    assert.equal(fixture.listeners.size, 0);
    complete();
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(delivered, false);
    assert.equal(fixture.calls.filter((request) => request.method === "plugins.communication.close").length, end === "dispose" ? 1 : 0);
  });
}

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

test("readiness and a no-op runtime notification keep subscriptions and pending context alive", async () => {
  const fixture = host();
  const client = createPluginCommunicationClient("demo", fixture.options);
  let heard = 0;
  await client.events.on("changed", () => { heard += 1; });
  fixture.emit("plugins.changed", { generation: 1, plugin_id: "another", kind: "ui" });
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
  assert.deepEqual(replies[0].payload.error, { code: "plugin_handler_failed", message: "插件后台执行失败", details: { detail: "binding failed" } });
  await client.dispose();
  assert.equal(fixture.calls.at(-1)?.method, "plugins.communication.close");
});
