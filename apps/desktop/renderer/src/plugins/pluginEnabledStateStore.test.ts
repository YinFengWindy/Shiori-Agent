import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import type { PluginSummary } from "./pluginBridgeClient";
import {
  ensurePluginEnabledStateLoaded,
  getPluginEnabledPredicate,
  isPluginEnabled,
  resetPluginEnabledStateForTests,
  setPluginEnabledSnapshot,
  subscribePluginEnabledState,
  refreshPluginEnabledState,
  registerPluginUiSynchronization,
} from "./pluginEnabledStateStore.js";

afterEach(() => resetPluginEnabledStateForTests());

describe("pluginEnabledStateStore", () => {
  it("treats a plugin unknown to the cache as disabled, not enabled (no fail-open flash)", () => {
    assert.equal(isPluginEnabled("never-seen"), false);
  });

  it("still treats an unrecognized plugin as disabled after the roster has loaded", () => {
    setPluginEnabledSnapshot([{ id: "demo", enabled: true, state: "ACTIVE" }]);
    assert.equal(isPluginEnabled("some-other-plugin"), false);
  });

  it("exposes a predicate whose identity changes whenever the cache changes", () => {
    const before = getPluginEnabledPredicate();
    setPluginEnabledSnapshot([{ id: "demo", enabled: true, state: "ACTIVE" }]);
    const afterSnapshot = getPluginEnabledPredicate();
    setPluginEnabledSnapshot([{ id: "demo", enabled: false, state: "DISABLED" }]);
    const afterToggle = getPluginEnabledPredicate();

    assert.notEqual(before, afterSnapshot);
    assert.notEqual(afterSnapshot, afterToggle);
    // Calling it again without any change returns the exact same reference,
    // which is required for useSyncExternalStore to avoid re-rendering forever.
    assert.equal(getPluginEnabledPredicate(), afterToggle);
  });

  it("fetches the roster once and memoizes it across callers", async () => {
    let calls = 0;
    const client = { listPlugins: async () => { calls += 1; return [{ id: "demo", enabled: false, state: "DISABLED" } as never]; } };

    await ensurePluginEnabledStateLoaded(client);
    await ensurePluginEnabledStateLoaded(client);

    assert.equal(calls, 1);
    assert.equal(isPluginEnabled("demo"), false);
  });

  it("coalesces concurrent loads into a single request", async () => {
    let calls = 0;
    let resolveFetch!: (value: Array<{ id: string; enabled: boolean; state: string }>) => void;
    const client = {
      listPlugins: async () => {
        calls += 1;
        return new Promise<Array<{ id: string; enabled: boolean; state: string }>>((resolve) => { resolveFetch = resolve; });
      },
    };

    const first = ensurePluginEnabledStateLoaded(client as never);
    const second = ensurePluginEnabledStateLoaded(client as never);
    await Promise.resolve();
    resolveFetch([{ id: "demo", enabled: true, state: "ACTIVE" }]);
    await Promise.all([first, second]);

    assert.equal(calls, 1);
  });

  it("serializes authoritative snapshots and retains UI synchronization after every publication", async () => {
    const events: string[] = [];
    let finishImport!: () => void;
    const importing = new Promise<void>((resolve) => { finishImport = resolve; });
    let started!: () => void;
    const importStarted = new Promise<void>((resolve) => { started = resolve; });
    let calls = 0;
    const client = { listPlugins: async () => {
      calls += 1;
      events.push(`list ${calls}`);
      const plugin: PluginSummary = {
        id: "demo", candidateId: "workspace/demo", source: "workspace", directory: "workspace/demo", name: "demo", version: "1.0.0", description: "",
        enabled: calls === 1, canToggle: true, state: calls === 1 ? "ACTIVE" : "DISABLED", error: "", diagnostic: null, hasConfigSchema: false, supportsHotUnload: true,
        rendererUi: calls === 1 ? { pluginId: "demo", entry: "granted", css: [] } : undefined,
      };
      return [plugin];
    } };
    registerPluginUiSynchronization(async (entries) => {
      events.push(`sync ${entries.length}`);
      if (entries.length) { started(); await importing; }
      return new Map();
    });
    const first = refreshPluginEnabledState(client);
    await importStarted;
    const second = refreshPluginEnabledState(client);
    assert.equal(calls, 1);
    finishImport();
    await Promise.all([first, second]);
    assert.deepEqual(events, ["list 1", "sync 1", "list 2", "sync 0"]);
    assert.equal(isPluginEnabled("demo"), false);
  });

  it("notifies subscribers when the snapshot or a single flag changes", () => {
    let notifications = 0;
    const unsubscribe = subscribePluginEnabledState(() => { notifications += 1; });

    setPluginEnabledSnapshot([{ id: "demo", enabled: true, state: "ACTIVE" }]);
    assert.equal(isPluginEnabled("demo"), true);
    setPluginEnabledSnapshot([{ id: "demo", enabled: false, state: "DISABLED" }]);
    assert.equal(isPluginEnabled("demo"), false);

    assert.equal(notifications, 2);
    unsubscribe();
  });
});
