import assert from "node:assert/strict";
import { test } from "node:test";
import { managedQQStatus } from "./qqStatusPresentation";
import type { ManagedStatus } from "./useManagedNapCat";

const status: ManagedStatus = {
  preparation: { stage: "ready", percent: 100, version: "v4" },
  login: { phase: "login_required", login_phase: "waiting_qrcode", qrcode: "", error: "" },
  connection: "login_required",
  error: "",
};

test("QQ QR waiting phases render as normal Chinese status", () => {
  assert.deepEqual(managedQQStatus(status), { label: "正在获取二维码", tone: "accent" });
  assert.deepEqual(managedQQStatus({ ...status, login: { ...status.login, qrcode: "data:image/png;base64,QR" } }),
    { label: "等待扫码登录", tone: "accent" });
  assert.deepEqual(managedQQStatus({ ...status, connection: "online" }), { label: "在线", tone: "success" });
  assert.deepEqual(managedQQStatus({ ...status, connection: "error", error: "socket failed" }),
    { label: "连接失败", tone: "danger" });
});
