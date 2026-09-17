import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { usePluginManagementController } from "./usePluginManagementController";
import { resetPluginEnabledStateForTests } from "./pluginEnabledStateStore";

/** The one row this test's fake `plugins.list` returns, mutated between snapshots. */
function pluginRow(state: string) {
  return {
    id: "demo", candidate_id: "workspace/demo", source: "workspace", directory: "workspace/demo",
    name: "demo", version: "1.0.0", description: "", enabled: true, can_toggle: true,
    state,
    error: state === "FAILED" ? "module threw" : "",
    diagnostic: state === "FAILED"
      ? { code: "renderer_ui_failed", stage: "ui", field: "renderer.ui.entry", reason: "module threw", path: "", state: "FAILED" }
      : null,
    has_config_schema: false, supports_hot_unload: true,
    pending_renderer_kinds: state === "ACTIVE" ? ["ui"] : [],
  };
}

test("a runtime.applied arrival while mounted refreshes a plugin's row without user action (#262 AC3)", async () => {
  resetPluginEnabledStateForTests();
  const listeners = new Set<(event: BridgeEvent) => void>();
  let state = "ACTIVE";
  let latest: ReturnType<typeof usePluginManagementController> | undefined;
  function Probe() {
    const controller = usePluginManagementController();
    useEffect(() => { latest = controller; });
    return null;
  }
  const view = await mountTestComponent(<Probe />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    invoke: async ({ method }: { method: string }) => {
      if (method === "plugins.list") {
        return { id: "r", type: "response", method, error: null, payload: { plugins: [pluginRow(state)] } };
      }
      return { id: "r", type: "response", method, error: null, payload: {} };
    },
  } } });
  try {
    // Drains the mount effect's own reload() before asserting the baseline.
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    assert.equal(latest?.plugins?.[0]?.state, "ACTIVE");
    assert.deepEqual(latest?.plugins?.[0]?.pendingRendererKinds, ["ui"]);

    // The backend rolls the plugin back on its own (a UI module that threw
    // after mount) and broadcasts `runtime.applied` — no toggle, no reload()
    // call from this hook's own mutation path.
    state = "FAILED";
    await act(async () => {
      for (const listener of [...listeners]) {
        listener({ id: "e", type: "event", method: "runtime.applied", payload: { changed: true } });
      }
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    assert.equal(latest?.plugins?.[0]?.state, "FAILED");
    assert.equal(latest?.plugins?.[0]?.error, "module threw");
    assert.equal(latest?.plugins?.[0]?.diagnostic?.stage, "ui");
  } finally {
    await view.cleanup();
  }
  assert.equal(listeners.size, 0, "the subscription must be released on unmount");
});
