import assert from "node:assert/strict";
import { test } from "node:test";
import { managedQQStatus, napCatDetail } from "./qqStatusPresentation";
import type { ManagedStatus } from "./useManagedNapCat";

const status: ManagedStatus = {
  preparation: { stage: "ready", percent: 100, version: "v4" },
  login: { phase: "login_required", login_phase: "waiting_qrcode", qrcode: "", error: "" },
  connection: "login_required",
  error: "",
};

test("QQ QR waiting phases render as normal Chinese status", () => {
  assert.deepEqual(managedQQStatus(status, false), { label: "正在获取二维码", tone: "warning" });
  assert.deepEqual(managedQQStatus({ ...status, login: { ...status.login, qrcode: "data:image/png;base64,QR" } }, false),
    { label: "等待扫码登录", tone: "warning" });
  assert.deepEqual(managedQQStatus({ ...status, connection: "online" }, true), { label: "在线", tone: "success" });
  assert.deepEqual(managedQQStatus({ ...status, connection: "error", error: "socket failed" }, false),
    { label: "连接失败", tone: "danger" });
});

test("a finished login reads 登录成功，正在连接 until the host account is online, never 需要登录", () => {
  const loggedIn: ManagedStatus = { ...status, login: { phase: "online", qrcode: "", error: "" }, connection: "connecting" };
  assert.deepEqual(managedQQStatus(loggedIn, false), { label: "登录成功，正在连接", tone: "warning" });
  assert.deepEqual(managedQQStatus({ ...loggedIn, connection: "online" }, false), { label: "登录成功，正在连接", tone: "warning" });
  assert.deepEqual(managedQQStatus({ ...loggedIn, connection: "online" }, true), { label: "在线", tone: "success" });
});

test("NapCat progress names the stage and percent while preparing and disappears once connected", () => {
  assert.equal(napCatDetail({ ...status, preparation: { stage: "downloading", percent: 42, version: "v4" } }), "NapCat v4 · 下载中 42%");
  assert.equal(napCatDetail(status), "NapCat v4");
  assert.equal(napCatDetail({ ...status, connection: "online" }), "");
  assert.equal(napCatDetail(null), "");
});
