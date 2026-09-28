import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import type { AccountSnapshot } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { QQAccountDetail } from "./index";

test("QQ add connects once and shows QR only when login requires scanning", async () => {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const qrImage = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7ZcV8AAAAASUVORK5CYII=";
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true } as T;
      if (method === "accounts.begin") return { ref: "temporary-1" } as T;
      if (method === "accounts.start") return { ref: "temporary-1", account_id: "" } as T;
      if (method === "accounts.managed_status") return {
        preparation: { stage: "ready", percent: 100, version: "v4.18.28" },
        login: { phase: "login_required", login_phase: "waiting_qrcode", qrcode: qrImage, error: "" },
        connection: "login_required", error: "等待 QQ 扫码登录",
      } as T;
      if (method === "accounts.refresh_qrcode" || method === "accounts.stop" || method === "accounts.cancel") return {} as T;
      throw new Error(method);
    },
  };
  const view = await mountTestComponent(null);
  try {
    await view.render(<QQAccountDetail account={null} roleId="mira" onChanged={() => undefined}
      client={client} host={desktopPluginHostServices} />);
    const button = (label: string) => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.trim() === label);
    assert.equal(view.container.querySelector('input[type="url"]'), null);
    assert.equal(calls.some((row) => row.method === "accounts.begin" || row.method === "accounts.start"), false);
    await act(async () => button("连接")?.click());
    assert.deepEqual(calls.filter((row) => row.method === "accounts.begin" || row.method === "accounts.start").map((row) => row.method),
      ["accounts.begin", "accounts.start"]);
    assert.deepEqual(calls.find((row) => row.method === "accounts.begin")?.payload, { role_id: "mira" });
    assert.equal(view.container.querySelector<HTMLImageElement>('img[alt="QQ 登录二维码"]')?.getAttribute("src"), qrImage);
    assert.match(view.container.textContent ?? "", /等待扫码登录/);
    assert.doesNotMatch(view.container.textContent ?? "", /waiting_qrcode|等待 QQ 扫码登录|待连接|编辑/);
    assert.equal(view.container.querySelector('[role="alert"]'), null);
    assert.equal(button("连接"), undefined);
    assert.ok(button("刷新二维码"));
    assert.ok(button("停止"));
  } finally {
    await view.cleanup();
    assert.deepEqual(calls.find((row) => row.method === "accounts.cancel")?.payload,
      { ref: "temporary-1", role_id: "mira" });
  }
});

test("a saved QQ account connects with its existing session without showing QR", async () => {
  const calls: string[] = [];
  let connected = false;
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string): Promise<T> {
      calls.push(method);
      if (method === "accounts.settings") return { managed_available: true, account: { ref: "aa" } } as T;
      if (method === "accounts.managed_status") return {
        preparation: { stage: "ready", percent: 100, version: "v4.18.28" },
        login: { phase: connected ? "online" : "stopped", qrcode: "", error: "" },
        connection: connected ? "online" : "offline", error: "", account_id: "qq:101",
      } as T;
      if (method === "accounts.start") { connected = true; return { ref: "aa", account_id: "qq:101" } as T; }
      throw new Error(method);
    },
  };
  const account: AccountSnapshot = {
    id: "qq:101", pluginId: "qq", platform: "qq", platformAccountId: "101", configRef: "aa",
    displayName: "QQ", avatarUrl: "", roleId: "mira", runtimeActive: true, connection: "offline",
    capabilities: [], error: "", responseRules: { privateEnabled: true, groupEnabled: true,
      requireMention: false, blockedSenderIds: [], groupRules: [] },
  };
  const view = await mountTestComponent(<QQAccountDetail account={account} roleId="mira"
    onChanged={() => undefined} client={client} host={desktopPluginHostServices} />);
  try {
    const button = () => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.trim() === "连接");
    assert.ok(button());
    await act(async () => button()?.click());
    assert.equal(calls.includes("accounts.begin"), false);
    assert.equal(calls.includes("accounts.start"), true);
    assert.equal(view.container.querySelector('img[alt="QQ 登录二维码"]'), null);
    assert.match(view.container.textContent ?? "", /在线/);
    assert.equal(button(), undefined);
  } finally { await view.cleanup(); }
});
