import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { LiveRunState, LiveStatus } from "./liveContracts";
import { LiveRunPanel } from "./LiveRunPanel";
import type { LiveAction, LiveRunController } from "./useLiveRun";

function controller(state: LiveRunState | null, values: Partial<LiveRunController> = {}, acted: LiveAction[] = []): LiveRunController {
  const status: LiveStatus | null = state === null ? null : {
    role_id: "role", state, connection: "connected", room: { room_id: 9, title: "间" }, configured_room_id: 9, run_id: "run",
    queue_length: 0, generating: false, output_pending: false, connection_error: state === "running" ? "弹幕连接断开" : "",
    reply_error: "", stop_reason: "", counters: { received: 1, replied: 1 }, recent: [],
  };
  return { status, readError: "", actionError: "", pending: null, act: async (action) => { acted.push(action); }, reload: () => undefined, ...values };
}

async function mount(run: LiveRunController, blockedReason: string | null) {
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><LiveRunPanel run={run} blockedReason={blockedReason} disabled={false} /></PluginHostServicesProvider>);
  const button = (label: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label);
  return { view, button };
}

test("开始 is disabled with the reason a precondition is unmet, and enabled once none is", async () => {
  const acted: LiveAction[] = [];
  let ui = await mount(controller("idle", {}, acted), "未配置直播间");
  try {
    assert.equal(ui.button("开始")?.disabled, true);
    assert.equal(ui.view.container.querySelector('[data-testid="live-start-blocked"]')?.textContent, "未配置直播间");
  } finally { await ui.view.cleanup(); }
  ui = await mount(controller("stopped", {}, acted), null);
  try {
    assert.equal(ui.view.container.querySelector('[data-testid="live-start-blocked"]'), null);
    await act(async () => ui.button("开始")!.click());
    assert.deepEqual(acted, ["start"]);
  } finally { await ui.view.cleanup(); }
});

test("a running run offers pause and stop and shows its status and current error; a paused one offers resume", async () => {
  const acted: LiveAction[] = [];
  let ui = await mount(controller("running", {}, acted), "未登录 B 站");
  try {
    assert.equal(ui.button("开始"), undefined);
    assert.equal(ui.view.container.querySelector('[data-testid="live-start-blocked"]'), null, "a reason to not start means nothing mid-run");
    const text = ui.view.container.textContent ?? "";
    assert.match(text, /状态运行中/);
    assert.match(text, /直播间间（9）/);
    assert.match(text, /弹幕连接断开/);
    await act(async () => ui.button("暂停")!.click());
    await act(async () => ui.button("结束")!.click());
    assert.deepEqual(acted, ["pause", "stop"]);
  } finally { await ui.view.cleanup(); }
  ui = await mount(controller("paused", {}, acted), null);
  try {
    await act(async () => ui.button("继续")!.click());
    assert.deepEqual(acted, ["pause", "stop", "resume"]);
  } finally { await ui.view.cleanup(); }
});

test("a request in flight locks every control, and a refused start shows the backend's reason", async () => {
  let ui = await mount(controller("running", { pending: "pause" }), null);
  try {
    assert.equal(ui.button("暂停")?.disabled, true);
    assert.equal(ui.button("暂停")?.getAttribute("aria-busy"), "true");
    assert.equal(ui.button("结束")?.disabled, true);
  } finally { await ui.view.cleanup(); }
  ui = await mount(controller("idle", { actionError: "该角色未启用桌宠，无法开始直播互动" }), null);
  try {
    assert.match(ui.view.container.textContent ?? "", /该角色未启用桌宠，无法开始直播互动/);
  } finally { await ui.view.cleanup(); }
  ui = await mount(controller(null), null);
  try {
    assert.equal(ui.button("开始")?.disabled, true, "nothing starts before the status is known");
  } finally { await ui.view.cleanup(); }
});
