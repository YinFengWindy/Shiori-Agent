import assert from "node:assert/strict";
import { test } from "node:test";
import type { BackgroundEffectScope } from "./backgroundEffectScope";
import { PluginBackgroundHost, type PluginBackgroundHostDeps } from "./pluginBackgroundHost";
import type { BackgroundCtx } from "@yinfengwindy/shiori-sdk";
import type { PluginBackgroundEntry } from "./pluginBackgroundRegistry";

/** A fake ctx.effect-capable BackgroundCtx that just records what happened. */
function fakeCtx(pluginId: string, scope: BackgroundEffectScope, log: string[]): BackgroundCtx {
  return {
    surfaces: {} as BackgroundCtx["surfaces"],
    rpc: {} as BackgroundCtx["rpc"],
    events: { on: async () => () => {} },
    hostEvents: { on: () => {} },
    store: { read: () => Promise.resolve(null), write: () => Promise.resolve() },
    assets: { url: () => null },
    tray: { setEntry: () => {}, removeEntry: () => {} },
    reportFailure: () => {},
    effect(label, dispose) {
      scope.addEffect(label, () => { log.push(`${pluginId}:dispose:${label}`); return dispose(); });
    },
  };
}

function entry(pluginId: string, log: string[], onSetup?: (ctx: BackgroundCtx) => void): PluginBackgroundEntry {
  return {
    slot: "app.background",
    pluginId,
    setup(ctx) {
      log.push(`${pluginId}:setup`);
      // Every fixture plugin registers one teardown effect, so a test can
      // observe that disabling it actually disposes something rather than
      // merely removing it from `runningPluginIds()`.
      ctx.effect("noop", () => {});
      onSetup?.(ctx);
    },
  };
}

/** Roster + reconcile signal test double: lets a test flip enabled ids and fire the listener itself. */
function fakeRoster(initial: string[]) {
  let ids = new Set(initial);
  const listeners = new Set<Parameters<PluginBackgroundHostDeps["subscribeRosterChanged"]>[0]>();
  return {
    setEnabled: (next: string[]) => { ids = new Set(next); },
    fireRosterChanged: () => { for (const listener of listeners) listener("runtime"); },
    deps: {
      listEnabledPluginIds: () => Promise.resolve(new Set(ids)),
      subscribeRosterChanged: (listener: Parameters<PluginBackgroundHostDeps["subscribeRosterChanged"]>[0]) => { listeners.add(listener); return () => listeners.delete(listener); },
    },
  };
}

function makeDeps(overrides: Partial<PluginBackgroundHostDeps> & Pick<PluginBackgroundHostDeps, "registry">, log: string[]): PluginBackgroundHostDeps {
  return {
    listEnabledPluginIds: () => Promise.resolve(new Set()),
    subscribeRosterChanged: () => () => {},
    createCtx: (pluginId, scope) => fakeCtx(pluginId, scope, log),
    ...overrides,
  };
}

test("starts only registered plugins that are enabled", async () => {
  const log: string[] = [];
  const roster = fakeRoster(["a"]);
  const registry = { list: () => [entry("a", log), entry("b", log)] };
  const host = new PluginBackgroundHost(makeDeps({ registry, ...roster.deps }, log));

  await host.start();

  assert.deepEqual(log, ["a:setup"]);
  assert.deepEqual(host.runningPluginIds(), ["a"]);
});

test("generation publication disposes disabled plugins and replaces enabled sibling scopes", async () => {
  const log: string[] = [];
  const roster = fakeRoster(["a", "b"]);
  const registry = { list: () => [entry("a", log), entry("b", log)] };
  const host = new PluginBackgroundHost(makeDeps({ registry, ...roster.deps }, log));
  await host.start();
  log.length = 0;

  roster.setEnabled(["b"]);
  roster.fireRosterChanged();
  // reconcile() runs asynchronously off the roster-changed callback.
  await flushMicrotasks();

  assert.deepEqual(log, ["a:dispose:noop", "b:dispose:noop", "b:setup"]);
  assert.deepEqual(host.runningPluginIds(), ["b"], "the still-enabled sibling must receive a new generation scope");
});

test("a plugin enabled after startup gets setup called on the next reconcile", async () => {
  const log: string[] = [];
  const roster = fakeRoster([]);
  const registry = { list: () => [entry("a", log)] };
  const host = new PluginBackgroundHost(makeDeps({ registry, ...roster.deps }, log));
  await host.start();
  assert.deepEqual(host.runningPluginIds(), []);

  roster.setEnabled(["a"]);
  roster.fireRosterChanged();
  await flushMicrotasks();

  assert.deepEqual(host.runningPluginIds(), ["a"]);
});

test("a plugin with no background contribution is simply not in the registry, and is never touched", async () => {
  const log: string[] = [];
  const roster = fakeRoster(["a", "no-background-plugin"]);
  const registry = { list: () => [entry("a", log)] };
  const host = new PluginBackgroundHost(makeDeps({ registry, ...roster.deps }, log));

  await host.start();

  assert.deepEqual(host.runningPluginIds(), ["a"]);
});

test("stop() disposes every running plugin and unsubscribes from roster changes", async () => {
  const log: string[] = [];
  const roster = fakeRoster(["a", "b"]);
  const registry = { list: () => [entry("a", log), entry("b", log)] };
  const host = new PluginBackgroundHost(makeDeps({ registry, ...roster.deps }, log));
  await host.start();
  log.length = 0;

  await host.stop();

  assert.deepEqual(host.runningPluginIds(), []);
  assert.deepEqual(new Set(log), new Set(["a:dispose:noop", "b:dispose:noop"]));

  // A roster-changed fire after stop() must not resurrect anything: the
  // listener was unsubscribed.
  roster.fireRosterChanged();
  await flushMicrotasks();
  assert.deepEqual(host.runningPluginIds(), []);
});

test("a plugin whose setup() throws is reported and never counted as running", async () => {
  const log: string[] = [];
  const errors: Array<[string, string]> = [];
  const roster = fakeRoster(["broken", "ok"]);
  const registry = {
    list: () => [
      { slot: "app.background" as const, pluginId: "broken", setup: () => { throw new Error("boom"); } },
      entry("ok", log),
    ],
  };
  const host = new PluginBackgroundHost(makeDeps({
    registry,
    ...roster.deps,
    onError: (pluginId, phase) => errors.push([pluginId, phase]),
  }, log));

  await host.start();

  assert.deepEqual(host.runningPluginIds(), ["ok"]);
  assert.deepEqual(errors, [["broken", "setup"]]);
});

/** Lets queued microtasks (the host's internal reconcile chain) settle before assertions. */
function flushMicrotasks(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

test("a setup that throws part-way still disposes whatever it managed to register", async () => {
  const log: string[] = [];
  const errors: [string, string][] = [];
  // Registers a real effect, then fails. Before #226's review this stranded
  // the effect: the scope was dropped from `running` without being disposed,
  // so nothing — not even a later disable — could ever reclaim it.
  const halfway: PluginBackgroundEntry = {
    slot: "app.background",
    pluginId: "halfway",
    setup(ctx) {
      ctx.effect("subscription", () => {});
      throw new Error("boom");
    },
  };
  const registry = { list: () => [halfway] };
  const roster = fakeRoster(["halfway"]);
  const host = new PluginBackgroundHost({
    ...makeDeps({ registry, ...roster.deps }, log),
    onError: (pluginId, phase) => errors.push([pluginId, phase]),
  });

  await host.start();

  assert.deepEqual(host.runningPluginIds(), [], "a failed setup must not count as running");
  assert.ok(
    log.includes("halfway:dispose:subscription"),
    `the partially registered effect must be disposed, got ${JSON.stringify(log)}`,
  );
  assert.deepEqual(errors, [["halfway", "setup"]], "the setup failure is reported once");
});

test("a roster fetch that throws is reported rather than escaping as an unhandled rejection", async () => {
  const log: string[] = [];
  const errors: [string, string][] = [];
  const registry = { list: () => [entry("quiet", log)] };
  const host = new PluginBackgroundHost({
    ...makeDeps({ registry }, log),
    listEnabledPluginIds: () => Promise.reject(new Error("bridge down")),
    onError: (pluginId, phase) => errors.push([pluginId, phase]),
  });

  // Must not reject: the roster-changed subscriber fires and forgets, so an
  // escaping rejection here would be unobserved.
  await host.start();

  assert.deepEqual(errors, [["", "roster"]]);
  assert.deepEqual(host.runningPluginIds(), [], "nothing starts when the roster is unknown");
});

test("bridge exit disposes contexts without querying or implicitly restarting the unavailable bridge", async () => {
  const log: string[] = [];
  let reads = 0;
  let signal: Parameters<PluginBackgroundHostDeps["subscribeRosterChanged"]>[0] = () => {};
  const host = new PluginBackgroundHost(makeDeps({
    registry: { list: () => [entry("demo", log)] },
    listEnabledPluginIds: async () => { reads += 1; return new Set(["demo"]); },
    subscribeRosterChanged: (listener) => { signal = listener; return () => {}; },
  }, log));
  await host.start();
  signal("unavailable");
  await flushMicrotasks();
  assert.equal(reads, 1);
  assert.deepEqual(host.runningPluginIds(), []);
  signal("runtime");
  await flushMicrotasks();
  assert.equal(reads, 2);
  assert.deepEqual(host.runningPluginIds(), ["demo"]);
  await host.stop();
});


test("a roster update preserves sibling scopes and disposes only inactive plugins", async () => {
  const log: string[] = [];
  const roster = fakeRoster(["a", "b"]);
  let signal: Parameters<PluginBackgroundHostDeps["subscribeRosterChanged"]>[0] = () => {};
  const host = new PluginBackgroundHost(makeDeps({
    registry: { list: () => [entry("a", log), entry("b", log)] },
    ...roster.deps, subscribeRosterChanged: (listener) => { signal = listener; return () => {}; },
  }, log));
  await host.start(); log.length = 0;
  signal("roster"); await flushMicrotasks();
  assert.deepEqual(log, []);
  roster.setEnabled(["b"]); signal("roster"); await flushMicrotasks();
  assert.deepEqual(log, ["a:dispose:noop"]);
  roster.setEnabled(["a", "b"]); signal("roster"); await flushMicrotasks();
  assert.deepEqual(log, ["a:dispose:noop", "a:setup"]);
  await host.stop();
});

test("publication during initial setup is retained and recovers from a reload rejection", async () => {
  const log: string[] = [];
  let signal: Parameters<PluginBackgroundHostDeps["subscribeRosterChanged"]>[0] | undefined;
  let release!: () => void, entered!: () => void;
  const started = new Promise<void>((resolve) => { entered = resolve; });
  let setups = 0;
  const host = new PluginBackgroundHost(makeDeps({
    listEnabledPluginIds: async () => new Set(["demo"]),
    subscribeRosterChanged: (listener) => { signal = listener; return () => { signal = undefined; }; },
    registry: { list: () => [{ slot: "app.background", pluginId: "demo", setup: async (ctx) => {
      setups++; ctx.effect("scope", () => {});
      if (setups === 1) { entered(); await new Promise<void>((resolve) => { release = resolve; }); throw new Error("runtime_reloading"); }
    } }] },
  }, log));
  const starting = host.start(); await started;
  signal?.("runtime"); release(); await starting; await flushMicrotasks();
  assert.equal(setups, 2);
  assert.deepEqual(host.runningPluginIds(), ["demo"]);
  await host.stop(); assert.equal(signal, undefined);
});


test("successive publications during queued reconciles eventually retain only the latest scope", async () => {
  const log: string[] = [];
  const gates: Array<() => void> = [];
  let signal: Parameters<PluginBackgroundHostDeps["subscribeRosterChanged"]>[0] = () => {};
  let setups = 0;
  const host = new PluginBackgroundHost(makeDeps({
    listEnabledPluginIds: async () => new Set(["demo"]),
    subscribeRosterChanged: (listener) => { signal = listener; return () => {}; },
    registry: { list: () => [{ slot: "app.background", pluginId: "demo", setup: async (ctx) => {
      const generation = ++setups;
      ctx.effect(String(generation), () => {});
      if (generation < 3) {
        await new Promise<void>((resolve) => { gates.push(resolve); });
        throw new Error("runtime_reloading");
      }
    } }] },
  }, log));
  const starting = host.start(); await flushMicrotasks();
  signal("runtime"); gates[0](); await starting; await flushMicrotasks();
  assert.equal(setups, 2);
  signal("runtime"); gates[1](); await flushMicrotasks();
  assert.equal(setups, 3);
  assert.deepEqual(host.runningPluginIds(), ["demo"]);
  assert.deepEqual(log, ["demo:dispose:1", "demo:dispose:2"]);
  await host.stop();
  assert.deepEqual(log, ["demo:dispose:1", "demo:dispose:2", "demo:dispose:3"]);
});
