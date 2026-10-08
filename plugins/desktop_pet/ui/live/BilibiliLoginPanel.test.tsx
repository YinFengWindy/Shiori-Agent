import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { BilibiliLoginPanel } from "./BilibiliLoginPanel";
import type { BilibiliAccountController } from "./useBilibiliAccount";

const account = { uid: 42, uname: "测试主播" };

function controller(values: Partial<BilibiliAccountController>, calls: string[] = []): BilibiliAccountController {
  return {
    account: { state: "logged_out" }, qr: null, error: "", busy: false,
    reload: () => calls.push("reload"),
    startLogin: async () => { calls.push("start"); },
    cancelLogin: () => calls.push("cancel"),
    logout: async () => { calls.push("logout"); },
    ...values,
  };
}

async function mount(login: BilibiliAccountController) {
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><BilibiliLoginPanel login={login} disabled={false} /></PluginHostServicesProvider>);
  const labels = () => Array.from(view.container.querySelectorAll("button")).map((item) => item.textContent);
  const click = async (label: string) => { await act(async () => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label)!.click()); };
  return { view, labels, click, text: () => view.container.textContent ?? "" };
}

test("each account state offers only its own actions", async () => {
  const cases: Array<[Partial<BilibiliAccountController>, string[], RegExp | null]> = [
    [{ account: null }, [], /读取中…/],
    [{ account: { state: "logged_out" } }, ["扫码登录"], null],
    [{ account: { state: "logged_in", account } }, ["退出登录"], /测试主播（42）/],
    [{ account: { state: "invalid", account } }, ["重新扫码", "退出登录"], /测试主播（42）登录已失效/],
  ];
  for (const [values, labels, text] of cases) {
    const ui = await mount(controller(values));
    try {
      assert.deepEqual(ui.labels(), labels);
      if (text) assert.match(ui.text(), text);
    } finally { await ui.view.cleanup(); }
  }
});

test("a shown QR replaces the scan button; an expired one offers a fresh QR; cancel and logout call through", async () => {
  const calls: string[] = [];
  let ui = await mount(controller({ qr: { qrcode: "data:image/png;base64,a", scan: "waiting_confirm" } }, calls));
  try {
    assert.equal(ui.view.container.querySelector('img[alt="B 站登录二维码"]')?.getAttribute("src"), "data:image/png;base64,a");
    assert.match(ui.text(), /已扫码，等待确认/);
    assert.deepEqual(ui.labels(), ["取消"]);
    await ui.click("取消");
  } finally { await ui.view.cleanup(); }
  ui = await mount(controller({ account: { state: "invalid", account }, qr: { qrcode: "data:image/png;base64,a", scan: "expired" } }, calls));
  try {
    assert.match(ui.text(), /二维码已过期/);
    assert.deepEqual(ui.labels(), ["退出登录", "刷新二维码", "取消"]);
    await ui.click("刷新二维码");
    await ui.click("退出登录");
  } finally { await ui.view.cleanup(); }
  assert.deepEqual(calls, ["cancel", "start", "logout"]);
});

test("busy locks the account actions; a failed account read offers a retry", async () => {
  let ui = await mount(controller({ busy: true }));
  try {
    assert.equal(ui.view.container.querySelector("button")?.disabled, true);
  } finally { await ui.view.cleanup(); }
  const calls: string[] = [];
  ui = await mount(controller({ account: null, error: "网络错误" }, calls));
  try {
    assert.match(ui.text(), /网络错误/);
    await ui.click("重试");
    assert.deepEqual(calls, ["reload"]);
  } finally { await ui.view.cleanup(); }
});
