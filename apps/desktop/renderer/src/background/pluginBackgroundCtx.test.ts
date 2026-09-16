import assert from "node:assert/strict";
import { test } from "node:test";
import type {
  BridgeEvent,
  DesktopApi,
  DesktopSurfacesApi,
  SurfaceSettledPayload,
  TrayEntryClickedPayload,
} from "../../../src/bridge/shared";
import { unavailableLocalAssetUrl } from "../../../src/assets/localAssetContract";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { BackgroundEffectScope } from "./backgroundEffectScope";
import {
  createBackgroundCtx,
  type SurfaceSettledSource,
  type TrayClickSource,
} from "./pluginBackgroundCtx";

function fakeSurfaces(): DesktopSurfacesApi & { calls: unknown[][] } {
  const calls: unknown[][] = [];
  return {
    calls,
    create: (...args) => { calls.push(["create", ...args]); return Promise.resolve({ x: 0, y: 0, displayId: "d1" }); },
    destroy: (...args) => { calls.push(["destroy", ...args]); return Promise.resolve(); },
    show: (...args) => { calls.push(["show", ...args]); },
    hide: (...args) => { calls.push(["hide", ...args]); },
    workArea: (...args) => { calls.push(["workArea", ...args]); return Promise.resolve({ x: 0, y: 0, width: 0, height: 0 }); },
    setPosition: (...args) => { calls.push(["setPosition", ...args]); },
    moveTo: (...args) => { calls.push(["moveTo", ...args]); },
    post: (...args) => { calls.push(["post", ...args]); },
    setState: (...args) => { calls.push(["setState", ...args]); },
  };
}

/** A fake bridge event source that lets a test push events and inspect subscriber count. */
function fakeEventSource() {
  const listeners = new Set<(event: BridgeEvent) => void>();
  return {
    listenerCount: () => listeners.size,
    onEvent: (listener: (event: BridgeEvent) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    emit: (event: BridgeEvent) => { for (const listener of listeners) listener(event); },
  };
}

/** A fake settle source with the same shape as the preload's broadcast. */
function fakeSettledSource() {
  const listeners = new Set<(settled: SurfaceSettledPayload) => void>();
  return {
    listenerCount: () => listeners.size,
    onSurfaceSettled: ((listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }) as SurfaceSettledSource,
    emit: (settled: SurfaceSettledPayload) => { for (const listener of listeners) listener(settled); },
  };
}

function fakePluginData(): DesktopApi["pluginData"] & { calls: unknown[][]; stored: Map<string, unknown> } {
  const calls: unknown[][] = [];
  const stored = new Map<string, unknown>();
  return {
    calls,
    stored,
    read: (pluginId) => { calls.push(["read", pluginId]); return Promise.resolve(stored.get(pluginId) ?? null); },
    write: (pluginId, value) => { calls.push(["write", pluginId, value]); stored.set(pluginId, value); return Promise.resolve(); },
  };
}

/** A fake host tray that records calls and lets a test push clicks back. */
function fakeTray() {
  const calls: unknown[][] = [];
  const listeners = new Set<(payload: TrayEntryClickedPayload) => void>();
  return {
    calls,
    listenerCount: () => listeners.size,
    emit: (payload: TrayEntryClickedPayload) => { for (const listener of listeners) listener(payload); },
    api: {
      setEntry: (...args: unknown[]) => { calls.push(["setEntry", ...args]); },
      removeEntry: (...args: unknown[]) => { calls.push(["removeEntry", ...args]); },
      removeAllEntries: (...args: unknown[]) => { calls.push(["removeAllEntries", ...args]); },
      onEntryClicked: () => () => {},
    } as unknown as DesktopApi["tray"],
    onTrayEntryClicked: ((listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }) as TrayClickSource,
  };
}

const failingInvoke = (() => Promise.reject(new Error("unused"))) as DesktopInvoke;

function makeCtx(overrides: Partial<Parameters<typeof createBackgroundCtx>[0]> = {}) {
  const scope = overrides.scope ?? new BackgroundEffectScope();
  return createBackgroundCtx({
    pluginId: "demo",
    surfaces: fakeSurfaces(),
    invoke: failingInvoke,
    onEvent: () => () => {},
    onSurfaceSettled: () => () => {},
    pluginData: fakePluginData(),
    tray: fakeTray().api,
    onTrayEntryClicked: () => () => {},
    localAssetUrl: () => unavailableLocalAssetUrl,
    ...overrides,
    scope,
  });
}

test("ctx.surfaces binds the plugin id ahead of every call", async () => {
  const surfaces = fakeSurfaces();
  const ctx = makeCtx({ surfaces });

  await ctx.surfaces.create("main", { body: { width: 1, height: 1 } }, { x: 0, y: 0 });
  ctx.surfaces.show("main");
  ctx.surfaces.setPosition("main", { x: 1, y: 2 });

  assert.deepEqual(surfaces.calls, [
    ["create", "demo", "main", { body: { width: 1, height: 1 } }, { x: 0, y: 0 }],
    ["show", "demo", "main"],
    ["setPosition", "demo", "main", { x: 1, y: 2 }],
  ]);
});

test("ctx.rpc scopes calls to plugin.<id>.* and returns the unwrapped payload", async () => {
  const requests: unknown[] = [];
  const invoke: DesktopInvoke = (request) => {
    if (request.method === "plugins.communication.open") return Promise.resolve({ id: "open", type: "response", method: request.method, payload: { generation: "g1" }, error: null });
    requests.push(request);
    return Promise.resolve({ id: "x", type: "response", method: request.method, payload: { ok: true }, error: null });
  };
  const ctx = makeCtx({ invoke });

  const result = await ctx.rpc.call<{ ok: boolean }>("doThing", { a: 1 });

  assert.deepEqual(requests, [{ method: "plugin.demo.doThing", payload: { a: 1, __plugin_context: { plugin_id: "demo", generation: "g1" } } }]);
  assert.deepEqual(result, { ok: true });
});

test("ctx.events.on filters by method and ignores everything else", () => {
  const source = fakeEventSource();
  const ctx = makeCtx({ onEvent: source.onEvent });

  const received: unknown[] = [];
  ctx.hostEvents.on("demo.thing.happened", (payload) => received.push(payload));

  source.emit({ id: "1", type: "event", method: "demo.thing.happened", payload: { n: 1 } });
  source.emit({ id: "2", type: "event", method: "unrelated.event", payload: { n: 2 } });

  assert.deepEqual(received, [{ n: 1 }]);
});

test("ctx.events preserves the complete producer envelope for proactive consumers", async () => {
  const source = fakeEventSource();
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({ onEvent: source.onEvent, scope });
  const received: BridgeEvent[] = [];
  ctx.hostEvents.on("session.updated", (_payload, event) => received.push(event));
  const event: BridgeEvent = { id: "proactive", type: "event", method: "session.updated", payload: { role_id: "mira" } };
  source.emit(event);
  assert.deepEqual(received, [event]);
  await scope.disposeAll();
  source.emit(event);
  assert.equal(received.length, 1);
  assert.equal(source.listenerCount(), 0);
});

test("ctx.events.on registers its unsubscribe as an event-phase effect, released on disposeAll", async () => {
  const source = fakeEventSource();
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({ onEvent: source.onEvent, scope });

  ctx.hostEvents.on("demo.thing.happened", () => {});
  assert.equal(source.listenerCount(), 1);

  await scope.disposeAll();
  assert.equal(source.listenerCount(), 0, "subscription must be released on teardown");
});

test("ctx.effect's terminate always runs after ctx.events.on's unsubscribe, in #227's exact registration order", async () => {
  const order: string[] = [];
  // Wraps the fake source so unsubscribing is independently observable in
  // `order`, not just inferable from listener count.
  const source = fakeEventSource();
  const observedOnEvent = (listener: Parameters<typeof source.onEvent>[0]) => {
    const unsubscribe = source.onEvent(listener);
    return () => { order.push("unsubscribe"); unsubscribe(); };
  };
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({ onEvent: observedOnEvent, scope });

  // Natural, "readable" authoring order that broke the backend twice (#227):
  // subscribe first, register the terminate-style effect after.
  ctx.hostEvents.on("demo.thing.happened", () => {});
  ctx.effect("controller_terminate", () => { order.push("terminate"); });

  await scope.disposeAll();
  assert.deepEqual(order, ["unsubscribe", "terminate"]);
  assert.equal(source.listenerCount(), 0);
});

const settled = (overrides: Partial<SurfaceSettledPayload> = {}): SurfaceSettledPayload => ({
  pluginId: "demo",
  surfaceId: "main",
  placement: {
    anchor: { x: 3, y: 4 },
    bodyOffset: { x: 0, y: 0 },
    workArea: { x: 0, y: 0, width: 100, height: 100 },
  },
  reason: "drag",
  displayId: "d1",
  ...overrides,
});

test("ctx.surfaces.onSettled sees its own surface and nothing else", () => {
  const source = fakeSettledSource();
  const ctx = makeCtx({ onSurfaceSettled: source.onSurfaceSettled });

  const received: unknown[] = [];
  ctx.surfaces.onSettled("main", (value) => received.push(value));

  source.emit(settled());
  // Another surface of the same plugin, and another plugin's surface with the
  // same surface id: neither is this subscription's business.
  source.emit(settled({ surfaceId: "other" }));
  source.emit(settled({ pluginId: "rival" }));

  assert.deepEqual(received, [{
    placement: settled().placement,
    reason: "drag",
    displayId: "d1",
  }]);
});

test("ctx.surfaces.onSettled releases its subscription in the event phase, before ctx.effect", async () => {
  const order: string[] = [];
  const source = fakeSettledSource();
  const observed: SurfaceSettledSource = (listener) => {
    const unsubscribe = source.onSurfaceSettled(listener);
    return () => { order.push("unsubscribe"); unsubscribe(); };
  };
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({ onSurfaceSettled: observed, scope });

  ctx.surfaces.onSettled("main", () => {});
  ctx.effect("controller_terminate", () => { order.push("terminate"); });
  assert.equal(source.listenerCount(), 1);

  await scope.disposeAll();
  assert.deepEqual(order, ["unsubscribe", "terminate"]);
  assert.equal(source.listenerCount(), 0);
});

test("ctx.store binds the plugin id, so a plugin cannot read another's data by mistake", async () => {
  const pluginData = fakePluginData();
  const ctx = makeCtx({ pluginData });

  assert.equal(await ctx.store.read(), null);
  await ctx.store.write({ visible: true });

  assert.deepEqual(pluginData.calls, [
    ["read", "demo"],
    ["write", "demo", { visible: true }],
  ]);
  assert.deepEqual(pluginData.stored.get("demo"), { visible: true });
});

test("ctx.assets.url answers null for a path the host never granted", () => {
  const granted = new Map([["C:/roles/mira/sheet.webp", "shiori-asset://local/token-1"]]);
  const ctx = makeCtx({
    localAssetUrl: (path) => granted.get(path) ?? unavailableLocalAssetUrl,
  });

  assert.equal(ctx.assets.url("C:/roles/mira/sheet.webp"), "shiori-asset://local/token-1");
  // The placeholder URL means "no grant", and a plugin deciding whether it can
  // show a package must not mistake it for one.
  assert.equal(ctx.assets.url("C:/roles/mira/missing.webp"), null);
  assert.equal(ctx.assets.url(""), null);
});

test("ctx.tray binds the plugin id and routes clicks to the right handler", () => {
  const tray = fakeTray();
  const ctx = makeCtx({ tray: tray.api, onTrayEntryClicked: tray.onTrayEntryClicked });

  const clicked: string[] = [];
  ctx.tray.setEntry("toggle", { label: "显示桌宠", onClick: () => clicked.push("toggle") });
  ctx.tray.setEntry("settings", { label: "桌宠设置", enabled: false, onClick: () => clicked.push("settings") });

  assert.deepEqual(tray.calls, [
    ["setEntry", "demo", "toggle", { label: "显示桌宠", enabled: undefined }],
    ["setEntry", "demo", "settings", { label: "桌宠设置", enabled: false }],
  ]);

  tray.emit({ pluginId: "demo", entryId: "settings" });
  // Another plugin's click on an id this plugin also uses must not run this
  // plugin's handler.
  tray.emit({ pluginId: "rival", entryId: "toggle" });
  tray.emit({ pluginId: "demo", entryId: "toggle" });

  assert.deepEqual(clicked, ["settings", "toggle"]);
});

test("rewriting an entry replaces its handler rather than stacking another", () => {
  const tray = fakeTray();
  const ctx = makeCtx({ tray: tray.api, onTrayEntryClicked: tray.onTrayEntryClicked });

  const clicked: string[] = [];
  ctx.tray.setEntry("toggle", { label: "显示桌宠", onClick: () => clicked.push("show") });
  ctx.tray.setEntry("toggle", { label: "隐藏桌宠", onClick: () => clicked.push("hide") });

  tray.emit({ pluginId: "demo", entryId: "toggle" });

  // The pet rewrites this item on every show/hide; an accumulating handler
  // list would make one click do both.
  assert.deepEqual(clicked, ["hide"]);
  assert.equal(tray.listenerCount(), 1, "one click subscription, however many setEntry calls");
});

test("ctx.tray subscribes to clicks only once, and only when the plugin uses it", () => {
  const tray = fakeTray();
  const ctx = makeCtx({ tray: tray.api, onTrayEntryClicked: tray.onTrayEntryClicked });

  assert.equal(tray.listenerCount(), 0, "a plugin with no tray item must not subscribe");

  ctx.tray.setEntry("toggle", { label: "显示桌宠", onClick: () => {} });
  ctx.tray.setEntry("settings", { label: "桌宠设置", onClick: () => {} });

  assert.equal(tray.listenerCount(), 1);
});

test("teardown cuts tray clicks before reclaiming the entries, and reclaims them host-side", async () => {
  // One ordered log for both steps. Recording them in separate arrays would
  // assert that each happened but never that the unsubscribe came first —
  // which is the whole point, and is exactly what a single-phase scope would
  // get wrong (LIFO would reclaim the entries first).
  const order: string[] = [];
  const tray = fakeTray();
  const observed: TrayClickSource = (listener) => {
    const unsubscribe = tray.onTrayEntryClicked(listener);
    return () => { order.push("unsubscribe"); unsubscribe(); };
  };
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({
    tray: {
      ...tray.api,
      removeAllEntries: (pluginId: string) => {
        order.push(`removeAllEntries:${pluginId}`);
        tray.api.removeAllEntries(pluginId);
      },
    },
    onTrayEntryClicked: observed,
    scope,
  });
  ctx.tray.setEntry("toggle", { label: "显示桌宠", onClick: () => order.push("clicked") });
  tray.calls.length = 0;

  await scope.disposeAll();

  // #227's phase rule applied to the tray: a click landing mid-teardown must
  // not reach a plugin that is being disposed, so the subscription is cut
  // before the entries it drives are reclaimed.
  assert.deepEqual(order, ["unsubscribe", "removeAllEntries:demo"]);
  assert.equal(tray.listenerCount(), 0);
  // One host-side call, not a replay of removeEntry per id: the host owns the
  // menu, so this reclaims everything even if this side's bookkeeping drifted.
  assert.deepEqual(tray.calls, [["removeAllEntries", "demo"]]);
});

test("removeEntry drops the handler, so a stale click does nothing", () => {
  const tray = fakeTray();
  const ctx = makeCtx({ tray: tray.api, onTrayEntryClicked: tray.onTrayEntryClicked });
  const clicked: string[] = [];
  ctx.tray.setEntry("toggle", { label: "显示桌宠", onClick: () => clicked.push("toggle") });

  ctx.tray.removeEntry("toggle");
  tray.emit({ pluginId: "demo", entryId: "toggle" });

  assert.deepEqual(clicked, []);
  assert.deepEqual(tray.calls.at(-1), ["removeEntry", "demo", "toggle"]);
});

test("a setEntry that lands after teardown does not put the item back", async () => {
  const tray = fakeTray();
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({ tray: tray.api, onTrayEntryClicked: tray.onTrayEntryClicked, scope });
  ctx.tray.setEntry("toggle", { label: "显示桌宠", onClick: () => {} });

  await scope.disposeAll();
  tray.calls.length = 0;

  // A plugin can have an await in flight across being disabled — the pet
  // persists its position outside its own operation queue, so a store write
  // can return after teardown and drive one more refresh. Writing the entry
  // back would leave a menu item whose click subscription is already cut:
  // it outlives its plugin and does nothing when clicked, until the next
  // launch.
  ctx.tray.setEntry("toggle", { label: "隐藏桌宠", onClick: () => {} });
  ctx.tray.removeEntry("toggle");

  assert.deepEqual(tray.calls, []);
});

test("late event registrations cannot leak after scope disposal", async () => {
  const source = fakeEventSource();
  const settled = fakeSettledSource();
  const scope = new BackgroundEffectScope();
  const ctx = makeCtx({ onEvent: source.onEvent, onSurfaceSettled: settled.onSurfaceSettled, scope });
  await scope.disposeAll();
  assert.throws(() => ctx.hostEvents.on("chat.done", () => {}), /已处置/);
  assert.throws(() => ctx.surfaces.onSettled("main", () => {}), /已处置/);
  await assert.rejects(ctx.events.on("changed", () => {}), { code: "plugin_unavailable" });
  assert.equal(source.listenerCount(), 0);
  assert.equal(settled.listenerCount(), 0);
});
