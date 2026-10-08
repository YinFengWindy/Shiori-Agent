import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { LiveRunState, LiveStatus } from "./liveContracts";
import { liveStatusPollIntervalMs, useLiveRun, type LiveRunController } from "./useLiveRun";

function status(state: LiveRunState, queue_length = 0): LiveStatus {
  return {
    role_id: "role", state, connection: state === "idle" ? null : "connected", room: state === "idle" ? null : { room_id: 1, title: "间" },
    configured_room_id: 1, run_id: state === "idle" ? null : "run", queue_length, generating: false, output_pending: false,
    connection_error: "", reply_error: "", stop_reason: "", counters: {}, recent: [],
  };
}

function Run({ client, open, onRender }: { client: PluginRpcClient; open: boolean; onRender(run: LiveRunController): void }) {
  onRender(useLiveRun(client, "role", open));
  return null;
}

/** `live.status` answers from `current`, or from a test-held promise when `hold` is set. */
async function mountRun(initial: LiveRunState) {
  let current = status(initial);
  const reads: Array<ReturnType<typeof deferred<LiveStatus>> | null> = [];
  const state = { hold: false, latest: null as LiveRunController | null, renders: 0 };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    assert.equal(payload?.role_id, "role");
    if (method === "live.status") {
      if (!state.hold) { reads.push(null); return structuredClone(current) as T; }
      const answer = deferred<LiveStatus>(); reads.push(answer); return await answer.promise as T;
    }
    if (method === "live.start") { current = status("running"); return structuredClone(current) as T; }
    if (method === "live.stop") { current = { ...status("stopped"), stop_reason: "已手动结束" }; return structuredClone(current) as T; }
    throw new Error(`unexpected ${method}`);
  } });
  const render = (open: boolean) => <Run client={client} open={open} onRender={(run) => { state.latest = run; state.renders += 1; }} />;
  const view = await mountTestComponent(render(true));
  return { view, reads, state, render, set: (next: LiveStatus) => { current = next; } };
}

test("an idle run is read once on open and not polled; an active run is polled while open", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const ui = await mountRun("idle");
  try {
    assert.equal(ui.reads.length, 1);
    assert.equal(ui.state.latest?.status?.state, "idle");
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs * 3));
    assert.equal(ui.reads.length, 1, "nothing to poll while idle");

    await act(async () => ui.state.latest!.act("start"));
    assert.equal(ui.state.latest?.status?.state, "running");
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs));
    assert.equal(ui.reads.length, 2);
    const renders = ui.state.renders;
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs));
    assert.equal(ui.reads.length, 3);
    assert.equal(ui.state.renders, renders, "an unchanged status re-renders nothing");

    ui.set(status("running", 4));
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs));
    assert.equal(ui.state.latest?.status?.queue_length, 4);

    await ui.view.render(ui.render(false));
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs * 3));
    assert.equal(ui.reads.length, 4, "a closed dialog does not poll");
    await ui.view.render(ui.render(true));
    assert.equal(ui.reads.length, 5, "reopening reads at once");

    await act(async () => ui.state.latest!.act("stop"));
    assert.equal(ui.state.latest?.status?.stop_reason, "已手动结束");
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs * 3));
    assert.equal(ui.reads.length, 5, "a stopped run is no longer polled");
  } finally { await ui.view.cleanup(); }
});

test("a status read started before a run-control request never undoes its answer", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const ui = await mountRun("running");
  try {
    ui.state.hold = true;
    await act(async () => t.mock.timers.tick(liveStatusPollIntervalMs));
    assert.equal(ui.reads.length, 2);
    await act(async () => ui.state.latest!.act("stop"));
    assert.equal(ui.state.latest?.status?.state, "stopped");
    await act(async () => ui.reads[1]!.resolve(status("running")));
    assert.equal(ui.state.latest?.status?.state, "stopped");
  } finally { await ui.view.cleanup(); }
});

test("a refused start keeps the backend's reason", async () => {
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    if (method === "live.status") return status("idle") as T;
    throw new Error("桌宠语音未开启或未选择 TTS 服务，无法开始直播互动");
  } });
  let latest: LiveRunController | null = null;
  const view = await mountTestComponent(<Run client={client} open onRender={(run) => { latest = run; }} />);
  try {
    await act(async () => latest!.act("start"));
    assert.equal(latest!.actionError, "桌宠语音未开启或未选择 TTS 服务，无法开始直播互动");
    assert.equal(latest!.pending, null);
  } finally { await view.cleanup(); }
});
