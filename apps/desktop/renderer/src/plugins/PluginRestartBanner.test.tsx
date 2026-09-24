import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { getFeedbackSnapshot, resetFeedback } from "../shared/feedback/feedbackStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { PluginSummary } from "./pluginBridgeClient";
import { PluginRestartBanner, pluginsAwaitingRestart } from "./PluginRestartBanner";

afterEach(() => resetFeedback());

function plugin(overrides: Partial<PluginSummary>): PluginSummary {
  return { id: "demo", candidateId: "demo", name: "Demo", state: "ACTIVE", enabled: true, ...overrides } as PluginSummary;
}

describe("pluginsAwaitingRestart", () => {
  it("counts staged package operations, pending trust and restart-required plugins only", () => {
    const pending = pluginsAwaitingRestart([
      plugin({ id: "install", pendingOperation: "install" }),
      plugin({ id: "trust", trustPendingRestart: true }),
      plugin({ id: "stuck", state: "RESTART_REQUIRED" }),
      plugin({ id: "active" }),
      plugin({ id: "failed", state: "FAILED" }),
    ]);
    assert.deepEqual(pending.map((item) => item.id), ["install", "trust", "stuck"]);
  });
});

describe("PluginRestartBanner", () => {
  it("stays hidden when nothing waits for a restart", async () => {
    const view = await mountTestComponent(<PluginRestartBanner plugins={[plugin({})]} />);
    try {
      assert.equal(view.container.innerHTML, "");
    } finally { await view.cleanup(); }
  });

  it("relaunches the app from its button and reports a refused relaunch", async () => {
    const relaunches: string[] = [];
    let allowed = false;
    const view = await mountTestComponent(
      <PluginRestartBanner plugins={[plugin({ pendingOperation: "update" }), plugin({ id: "b", trustPendingRestart: true })]} />,
      { windowGlobals: { miraDesktop: { relaunchApp: async () => { relaunches.push("relaunch"); return allowed; } } } },
    );
    try {
      assert.match(view.container.textContent ?? "", /有 2 项更改需要重启后生效/);
      const button = view.container.querySelector("button")!;
      await act(async () => button.click());
      assert.deepEqual(relaunches, ["relaunch"]);
      assert.equal(getFeedbackSnapshot()[0]?.tone, "error");
      assert.equal(button.disabled, false);
      allowed = true;
      await act(async () => button.click());
      assert.equal(relaunches.length, 2);
      assert.equal(button.textContent, "正在重启…");
    } finally { await view.cleanup(); }
  });
});
