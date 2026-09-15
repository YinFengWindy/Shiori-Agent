import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {
  ensurePluginEnabledStateLoaded,
  getPluginEnabledPredicate,
  isPluginEnabled,
  resetPluginEnabledStateForTests,
  setPluginEnabledSnapshot,
  subscribePluginEnabledState,
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
    resolveFetch([{ id: "demo", enabled: true, state: "ACTIVE" }]);
    await Promise.all([first, second]);

    assert.equal(calls, 1);
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
