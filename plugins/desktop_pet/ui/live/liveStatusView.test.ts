import assert from "node:assert/strict";
import { test } from "node:test";
import type { LiveStatus } from "./liveContracts";
import { isRunActive, liveStatusErrors, liveStatusRows, startBlockedReason } from "./liveStatusView";

const loggedIn = { state: "logged_in", account: { uid: 1, uname: "主播" } } as const;

function status(values: Partial<LiveStatus>): LiveStatus {
  return {
    role_id: "role", state: "idle", connection: null, room: null, configured_room_id: null, run_id: null,
    queue_length: 0, generating: false, output_pending: false, connection_error: "", reply_error: "", stop_reason: "",
    counters: {}, recent: [], ...values,
  };
}

test("start is blocked in the backend gate's order (pet, room, TTS, login), silently while a fact is unknown", () => {
  const ready = { petEnabled: true, roomId: 1, speechReady: true, account: loggedIn } as const;
  assert.equal(startBlockedReason({ ...ready, petEnabled: false, roomId: null, speechReady: false }), "未启用桌宠");
  assert.equal(startBlockedReason({ ...ready, roomId: undefined }), "", "settings still loading are not 'no room'");
  assert.equal(startBlockedReason({ ...ready, roomId: null, speechReady: false, account: { state: "logged_out" } }), "未配置直播间");
  assert.equal(startBlockedReason({ ...ready, speechReady: null }), "");
  assert.equal(startBlockedReason({ ...ready, speechReady: false, account: { state: "logged_out" } }), "未开启桌宠语音");
  assert.equal(startBlockedReason({ ...ready, account: null }), "");
  assert.equal(startBlockedReason({ ...ready, account: { state: "logged_out" } }), "未登录 B 站");
  assert.equal(startBlockedReason({ ...ready, account: { ...loggedIn, state: "invalid" } }), "B 站登录已失效");
  assert.equal(startBlockedReason(ready), null);
});

test("a run lists its room, and the saved room too once it differs", () => {
  const running = status({ state: "running", connection: "reconnecting", room: { room_id: 100, title: "测试间" }, configured_room_id: 100, queue_length: 2, counters: { received: 5, replied: 3 } });
  assert.deepEqual(liveStatusRows(running), [
    { label: "状态", value: "运行中" },
    { label: "连接", value: "重连中" },
    { label: "直播间", value: "测试间（100）" },
    { label: "待处理", value: "2" },
    { label: "收到弹幕", value: "5" },
    { label: "已回复", value: "3" },
  ]);
  assert.deepEqual(liveStatusRows({ ...running, configured_room_id: 200 }).find((row) => row.label === "已配置直播间"), { label: "已配置直播间", value: "200" });
  assert.deepEqual(liveStatusRows({ ...running, configured_room_id: null }).find((row) => row.label === "已配置直播间"), { label: "已配置直播间", value: "未配置" });
});

test("idle shows only its state; a stopped run keeps its counts and reason, not a live connection", () => {
  assert.deepEqual(liveStatusRows(status({})), [{ label: "状态", value: "未开始" }]);
  const stopped = liveStatusRows(status({ state: "stopped", connection: "closed", room: { room_id: 1, title: "" }, configured_room_id: 1, stop_reason: "已手动结束" }));
  assert.equal(stopped.find((row) => row.label === "连接"), undefined);
  assert.equal(stopped.find((row) => row.label === "待处理"), undefined);
  assert.deepEqual(stopped.find((row) => row.label === "直播间"), { label: "直播间", value: "1" });
  assert.deepEqual(stopped.at(-1), { label: "结束原因", value: "已手动结束" });
  assert.equal(isRunActive(status({ state: "stopped" })), false);
  assert.equal(isRunActive(status({ state: "paused" })), true);
});

test("only current errors are listed", () => {
  assert.deepEqual(liveStatusErrors(status({ connection_error: "连接断开", reply_error: "" })), ["连接断开"]);
  assert.deepEqual(liveStatusErrors(status({})), []);
});
