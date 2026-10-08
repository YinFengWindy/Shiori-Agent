import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { BilibiliLoginPanel } from "./BilibiliLoginPanel";
import type { BilibiliLoginPoll } from "./liveContracts";
import { loginPollIntervalMs, useBilibiliAccount } from "./useBilibiliAccount";

type Request = { method: string; payload?: Record<string, unknown> };

function Login({ client, open }: { client: PluginRpcClient; open: boolean }) {
  return <BilibiliLoginPanel login={useBilibiliAccount(client, "role", open)} disabled={false} />;
}

/** A logged-out role whose polls the test answers one by one. */
async function mountLogin() {
  const requests: Request[] = [];
  const polls: Array<ReturnType<typeof deferred<BilibiliLoginPoll>>> = [];
  let qrs = 0;
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "bilibili.account.status") return { state: "logged_out" } as T;
    if (method === "bilibili.login.start") { qrs += 1; return { state: "waiting_scan", qrcode: `data:image/png;base64,qr${qrs}` } as T; }
    if (method === "bilibili.login.poll") { const answer = deferred<BilibiliLoginPoll>(); polls.push(answer); return await answer.promise as T; }
    if (method === "bilibili.account.logout") return { state: "logged_out" } as T;
    throw new Error(`unexpected ${method}`);
  } });
  const { host } = createFakeHostServices();
  const render = (open: boolean) => <PluginHostServicesProvider services={host}><Login client={client} open={open} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render(true));
  const button = (label: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label);
  const click = async (label: string) => { await act(async () => button(label)!.click()); };
  const text = () => view.container.textContent ?? "";
  const qr = () => view.container.querySelector<HTMLImageElement>('img[alt="B 站登录二维码"]');
  return { view, requests, polls, button, click, text, qr, render };
}

const pollCount = (requests: Request[]) => requests.filter((item) => item.method === "bilibili.login.poll").length;

test("the QR shows in place and is polled one request at a time until the scan is confirmed", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const ui = await mountLogin();
  try {
    await ui.click("扫码登录");
    assert.equal(ui.qr()?.getAttribute("src"), "data:image/png;base64,qr1");
    assert.match(ui.text(), /等待扫码/);
    assert.deepEqual(ui.requests.find((item) => item.method === "bilibili.login.start")?.payload, { role_id: "role" });

    await act(async () => t.mock.timers.tick(loginPollIntervalMs));
    await act(async () => t.mock.timers.tick(loginPollIntervalMs * 3));
    assert.equal(pollCount(ui.requests), 1, "an unanswered poll is never joined by another");
    await act(async () => ui.polls[0].resolve({ state: "waiting_confirm" }));
    assert.match(ui.text(), /已扫码，等待确认/);

    await act(async () => t.mock.timers.tick(loginPollIntervalMs));
    assert.equal(pollCount(ui.requests), 2);
    await act(async () => ui.polls[1].resolve({ state: "success", account: { uid: 42, uname: "测试主播" } }));
    assert.equal(ui.qr(), null);
    assert.match(ui.text(), /测试主播（42）/);
    assert.ok(ui.button("退出登录"));
    await act(async () => t.mock.timers.tick(loginPollIntervalMs * 5));
    assert.equal(pollCount(ui.requests), 2, "polling ends with the login");
  } finally { await ui.view.cleanup(); }
});

test("an expired QR stops polling and offers a fresh one; a cancelled QR ignores its late answer", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const ui = await mountLogin();
  try {
    await ui.click("扫码登录");
    await act(async () => t.mock.timers.tick(loginPollIntervalMs));
    await act(async () => ui.polls[0].resolve({ state: "expired" }));
    assert.match(ui.text(), /二维码已过期/);
    await act(async () => t.mock.timers.tick(loginPollIntervalMs * 5));
    assert.equal(pollCount(ui.requests), 1);

    await ui.click("刷新二维码");
    assert.equal(ui.qr()?.getAttribute("src"), "data:image/png;base64,qr2");
    await act(async () => t.mock.timers.tick(loginPollIntervalMs));
    assert.equal(pollCount(ui.requests), 2);
    await ui.click("取消");
    assert.equal(ui.qr(), null);
    await act(async () => ui.polls[1].reject(new Error("该 B 站扫码登录已被取消")));
    assert.doesNotMatch(ui.text(), /已被取消/, "the answer for a QR no longer shown changes nothing");
    assert.ok(ui.button("扫码登录"));
  } finally { await ui.view.cleanup(); }
});

test("a closed dialog does not poll; reopening resumes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const ui = await mountLogin();
  try {
    await ui.click("扫码登录");
    await ui.view.render(ui.render(false));
    await act(async () => t.mock.timers.tick(loginPollIntervalMs * 3));
    assert.equal(pollCount(ui.requests), 0);
    await ui.view.render(ui.render(true));
    await act(async () => t.mock.timers.tick(loginPollIntervalMs));
    assert.equal(pollCount(ui.requests), 1);
  } finally { await ui.view.cleanup(); }
});

test("an invalid login keeps its account beside a rescan, and a poll failure is shown", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const polls: Array<ReturnType<typeof deferred<BilibiliLoginPoll>>> = [];
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    if (method === "bilibili.account.status") return { state: "invalid", account: { uid: 7, uname: "旧账号" } } as T;
    if (method === "bilibili.login.start") return { state: "waiting_scan", qrcode: "data:image/png;base64,x" } as T;
    const answer = deferred<BilibiliLoginPoll>(); polls.push(answer); return await answer.promise as T;
  } });
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><Login client={client} open /></PluginHostServicesProvider>);
  try {
    const text = () => view.container.textContent ?? "";
    assert.match(text(), /旧账号（7）登录已失效/);
    await act(async () => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "重新扫码")!.click());
    await act(async () => t.mock.timers.tick(loginPollIntervalMs));
    await act(async () => polls[0].reject(new Error("B 站扫码成功但登录态校验未通过，请重新扫码")));
    assert.match(text(), /登录态校验未通过/);
    assert.equal(view.container.querySelector("img"), null);
  } finally { await view.cleanup(); }
});
