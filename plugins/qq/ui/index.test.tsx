import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import type { AccountSnapshot } from "@shiori/plugin-sdk";
import { createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@shiori/plugin-sdk/testing";
import { QQAccountDetail } from "./index";

const savedAccount: AccountSnapshot = {
  id: "qq:101", pluginId: "qq", platform: "qq", platformAccountId: "101", configRef: "aa",
  displayName: "QQ", avatarUrl: "", roleId: "mira", runtimeActive: true, connection: "offline",
  capabilities: [], error: "", responseRules: { privateEnabled: true, groupEnabled: true,
    blockedSenderIds: [] },
};

const readyPreparation = { stage: "ready", percent: 100, version: "v4.18.28" };

const buttonIn = (root: ParentNode, label: string) => Array.from(root.querySelectorAll("button"))
  .find((item) => item.textContent?.trim() === label);

/** The status card's words, i.e. its dot label. */
const cardStatus = (root: ParentNode) => root.querySelector('[aria-label="连接状态"] [aria-live]')?.firstElementChild?.textContent;

test("QQ add connects once and shows QR only when login requires scanning", async () => {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const qrImage = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7ZcV8AAAAASUVORK5CYII=";
  const client = createFakePluginClient({
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
  });
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(null);
  try {
    // StrictMode replays mount effects; opening the add dialog must still begin exactly one login.
    await view.render(<React.StrictMode><QQAccountDetail account={null} roleId="mira" onChanged={() => undefined}
      client={client} host={host} /></React.StrictMode>);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    const button = (label: string) => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.trim() === label);
    assert.equal(view.container.querySelector('input[type="url"]'), null);
    assert.deepEqual(calls.filter((row) => row.method === "accounts.begin" || row.method === "accounts.start").map((row) => row.method),
      ["accounts.begin", "accounts.start"]);
    assert.deepEqual(calls.find((row) => row.method === "accounts.begin")?.payload, { role_id: "mira" });
    assert.equal(view.container.querySelector<HTMLImageElement>('img[alt="QQ 登录二维码"]')?.getAttribute("src"), qrImage);
    assert.match(view.container.textContent ?? "", /等待扫码登录/);
    assert.doesNotMatch(view.container.textContent ?? "", /waiting_qrcode|等待 QQ 扫码登录|待连接|编辑/);
    assert.equal(view.container.querySelector('[role="alert"]'), null);
    assert.equal(button("连接"), undefined);
    assert.ok(button("刷新二维码"));
    assert.ok(button("断开连接"));
  } finally {
    await view.cleanup();
    assert.deepEqual(calls.filter((row) => row.method === "accounts.cancel").map((row) => row.payload),
      [{ ref: "temporary-1", role_id: "mira" }]);
  }
});

test("a saved QQ account connects with its existing session: 正在连接 at once, then 登录成功，正在连接 until the host reports online", async () => {
  const calls: string[] = [];
  let connected = false;
  const started = deferred<void>();
  const client = createFakePluginClient({
    async call<T>(method: string): Promise<T> {
      calls.push(method);
      if (method === "accounts.settings") return { managed_available: true, account: { ref: "aa" } } as T;
      if (method === "accounts.managed_status") return {
        preparation: readyPreparation,
        login: { phase: connected ? "online" : "stopped", qrcode: "", error: "" },
        connection: connected ? "connecting" : "offline", error: "", account_id: "qq:101",
      } as T;
      if (method === "accounts.start") {
        await started.promise;
        connected = true;
        return { ref: "aa", account_id: "qq:101" } as T;
      }
      throw new Error(method);
    },
  });
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(<QQAccountDetail account={savedAccount} roleId="mira"
    onChanged={() => undefined} client={client} host={host} />);
  try {
    // Opening a saved offline account does not connect it by itself.
    assert.equal(calls.includes("accounts.start"), false);
    assert.equal(cardStatus(view.container), "已停止");
    await act(async () => buttonIn(view.container, "连接")?.click());
    // The request is in flight: its status shows at once and its button spins and waits.
    assert.equal(cardStatus(view.container), "正在连接");
    assert.equal(buttonIn(view.container, "连接")?.disabled, true);
    assert.equal(buttonIn(view.container, "连接")?.getAttribute("aria-busy"), "true");
    await act(async () => started.resolve());
    assert.equal(calls.includes("accounts.begin"), false);
    assert.equal(view.container.querySelector('img[alt="QQ 登录二维码"]'), null);
    // Logged in, but the host account is not online yet: not 需要登录.
    assert.equal(cardStatus(view.container), "登录成功，正在连接");
    assert.ok(buttonIn(view.container, "断开连接"));
    assert.equal(buttonIn(view.container, "连接"), undefined);
    await view.render(<QQAccountDetail account={{ ...savedAccount, connection: "online" }} roleId="mira"
      onChanged={() => undefined} client={client} host={host} />);
    assert.equal(cardStatus(view.container), "在线");
  } finally { await view.cleanup(); }
});

test("once the add-flow login is verified, 断开连接 disconnects that account instead of stopping the temporary login", async () => {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const changed: Array<string | undefined> = [];
  const client = createFakePluginClient({
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true } as T;
      if (method === "accounts.begin") return { ref: "temporary-1" } as T;
      if (method === "accounts.start") return { ref: "temporary-1", account_id: "" } as T;
      if (method === "accounts.managed_status") return {
        preparation: readyPreparation, login: { phase: "online", qrcode: "", error: "" },
        connection: "connecting", error: "", account_id: "qq:101",
      } as T;
      return {} as T;
    },
  });
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(<QQAccountDetail account={null} roleId="mira"
    onChanged={(accountId) => changed.push(accountId)} client={client} host={host} />);
  try {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    assert.deepEqual(changed, ["qq:101"]);
    // The host list has not caught up (account is still null), yet the login is verified.
    assert.equal(cardStatus(view.container), "登录成功，正在连接");
    await act(async () => buttonIn(view.container, "断开连接")?.click());
    assert.deepEqual(calls.find((row) => row.method === "accounts.disconnect")?.payload, { account_id: "qq:101" });
    assert.equal(calls.some((row) => row.method === "accounts.stop"), false);
  } finally { await view.cleanup(); }
});

test("退出登录 sits in the dialog's danger zone and shows 正在退出 while it runs", async () => {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const loggedOut = deferred<void>();
  const client = createFakePluginClient({
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true, account: { ref: "aa" } } as T;
      if (method === "accounts.managed_status") return {
        preparation: readyPreparation, login: { phase: "online", qrcode: "", error: "" },
        connection: "online", error: "", account_id: "qq:101",
      } as T;
      if (method === "accounts.logout") await loggedOut.promise;
      return {} as T;
    },
  });
  const fake = createFakeHostServices();
  const view = await mountTestComponent(null);
  const zone = fake.accountDetailActionsZone();
  try {
    await view.render(<QQAccountDetail account={{ ...savedAccount, connection: "online" }} roleId="mira"
      onChanged={() => undefined} client={client} host={fake.host} />);
    assert.equal(buttonIn(view.container, "退出登录"), undefined);
    await act(async () => buttonIn(zone, "退出登录")?.click());
    assert.deepEqual(calls.find((row) => row.method === "accounts.logout")?.payload, { account_id: "qq:101" });
    assert.equal(cardStatus(view.container), "正在退出");
    assert.equal(buttonIn(zone, "退出登录")?.disabled, true);
    assert.equal(buttonIn(view.container, "断开连接")?.disabled, true);
    await act(async () => loggedOut.resolve());
    assert.equal(buttonIn(zone, "退出登录")?.disabled, false);
  } finally { await view.cleanup(); }
});

test("a failed QQ settings read reports its cause without claiming the platform is unsupported", async () => {
  const { PluginBridgeError } = await import("@shiori/plugin-sdk");
  const fake = createFakeHostServices();
  const client = createFakePluginClient({ call: async () => { throw new PluginBridgeError("本地服务处理失败", "internal_error", { detail: "settings access denied" }); } });
  const view = await mountTestComponent(<QQAccountDetail account={savedAccount} roleId="mira" onChanged={() => undefined} host={fake.host} client={client} />);
  try {
    assert.doesNotMatch(view.container.textContent ?? "", /仅支持 Windows/);
    const error = fake.uiRenders.InlineError.at(-1);
    assert.equal(error?.message, "QQ 账号设置读取失败");
    assert.match(error?.detail ?? "", /settings access denied/);
  } finally { await view.cleanup(); }
});
