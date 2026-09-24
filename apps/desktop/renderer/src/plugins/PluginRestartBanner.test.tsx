import assert from "node:assert/strict";
import { afterEach, before, describe, it } from "node:test";
import { act } from "react";
import { setInFlightChatTurns } from "../shared/chatTurnActivity";
import { getFeedbackSnapshot, resetFeedback } from "../shared/feedback/feedbackStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { PluginSummary } from "./pluginBridgeClient";

// Imported after a DOM exists: the dialog library reads browser globals at module load.
let PluginRestartBanner: typeof import("./PluginRestartBanner").PluginRestartBanner;
let pluginsAwaitingRestart: typeof import("./PluginRestartBanner").pluginsAwaitingRestart;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ PluginRestartBanner, pluginsAwaitingRestart } = await import("./PluginRestartBanner"));
  await environment.cleanup();
});

afterEach(() => {
  resetFeedback();
  setInFlightChatTurns(0);
});

function plugin(overrides: Partial<PluginSummary>): PluginSummary {
  return { id: "demo", candidateId: "demo", name: "Demo", state: "ACTIVE", enabled: true, ...overrides } as PluginSummary;
}

async function flush() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
}

async function mountBanner(relaunchApp: () => Promise<boolean>) {
  return mountTestComponent(
    <PluginRestartBanner plugins={[plugin({ pendingOperation: "update" }), plugin({ id: "b", trustPendingRestart: true })]} />,
    { windowGlobals: { miraDesktop: { relaunchApp } } },
  );
}

function dialogButton(label: string) {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')).find((button) => button.textContent === label);
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

  it("relaunches straight away when no chat is running, and reports a refused relaunch", async () => {
    const relaunches: string[] = [];
    let allowed = false;
    const view = await mountBanner(async () => { relaunches.push("relaunch"); return allowed; });
    try {
      assert.match(view.container.textContent ?? "", /有 2 项更改需要重启后生效/);
      const button = view.container.querySelector("button")!;
      await act(async () => button.click());
      await flush();
      assert.equal(document.querySelector('[role="dialog"]'), null);
      assert.deepEqual(relaunches, ["relaunch"]);
      assert.equal(getFeedbackSnapshot()[0]?.tone, "error");
      assert.equal(button.disabled, false);
      allowed = true;
      await act(async () => button.click());
      assert.equal(relaunches.length, 2);
      assert.equal(button.textContent, "正在重启…");
    } finally { await view.cleanup(); }
  });

  it("asks before interrupting a running chat turn and relaunches only once confirmed", async () => {
    setInFlightChatTurns(1);
    const relaunches: string[] = [];
    const view = await mountBanner(async () => { relaunches.push("relaunch"); return true; });
    try {
      const button = view.container.querySelector("button")!;
      await act(async () => button.click());
      await flush();
      assert.deepEqual(relaunches, []);
      assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /有对话正在进行，重启会中断它/);
      await act(async () => dialogButton("取消")?.click());
      await flush();
      assert.deepEqual(relaunches, []);

      await act(async () => button.click());
      await flush();
      await act(async () => dialogButton("继续重启")?.click());
      assert.deepEqual(relaunches, ["relaunch"]);
    } finally { await view.cleanup(); }
  });
});
