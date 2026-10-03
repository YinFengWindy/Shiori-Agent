import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import { createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useQQAccountForm } from "./useQQAccountForm";

test("a temporary QQ login begins only when the user connects", async () => {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const client = createFakePluginClient({
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true } as T;
      if (method === "accounts.begin") return { ref: "temporary-1" } as T;
      if (method === "accounts.start") return { ref: "temporary-1", account_id: "" } as T;
      throw new Error(method);
    },
  });
  function Probe() {
    const form = useQQAccountForm({ roleId: "mira", client, onChanged: () => undefined,
      onCleanupError: (failure) => { throw failure; },
    });
    return <><output>{form.ref || "new"}</output><button type="button" onClick={() => void form.start()}>启动</button></>;
  }
  const view = await mountTestComponent(<Probe />);
  try {
    assert.deepEqual(calls.map((call) => call.method), ["accounts.settings"]);
    await act(async () => view.container.querySelector("button")?.click());
    assert.deepEqual(calls.map((call) => call.method), ["accounts.settings", "accounts.begin", "accounts.start"]);
    assert.deepEqual(calls[1].payload, { role_id: "mira" });
    assert.equal(calls[2].payload?.ref, "temporary-1");
    assert.equal(view.container.querySelector("output")?.textContent, "temporary-1");
  } finally { await view.cleanup(); }
});

test("closing before begin returns cancels the late temporary login", async () => {
  const calls: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  let finishBegin!: (result: { ref: string }) => void;
  const client = createFakePluginClient({
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true } as T;
      if (method === "accounts.begin") return new Promise<T>((resolve) => {
        finishBegin = (result) => resolve(result as T);
      });
      if (method === "accounts.cancel") return {} as T;
      throw new Error(method);
    },
  });
  function Probe() {
    const form = useQQAccountForm({ roleId: "mira", client, onChanged: () => undefined,
      onCleanupError: (failure) => { throw failure; },
    });
    return <button type="button" onClick={() => void form.start()}>连接</button>;
  }
  const view = await mountTestComponent(<Probe />);
  await act(async () => view.container.querySelector("button")?.click());
  await view.cleanup();
  await act(async () => finishBegin({ ref: "temporary-2" }));
  assert.deepEqual(calls.filter((call) => call.method !== "accounts.settings"), [
    { method: "accounts.begin", payload: { role_id: "mira" } },
    { method: "accounts.cancel", payload: { ref: "temporary-2", role_id: "mira" } },
  ]);
});


test("QQ account settings preserve an RPC diagnostic in the error disclosure", async () => {
  const { PluginBridgeError } = await import("@yinfengwindy/shiori-sdk");
  const client = createFakePluginClient({ call: async () => { throw new PluginBridgeError("本地服务处理失败", "internal_error", { detail: "settings read failed" }); } });
  let latest!: ReturnType<typeof useQQAccountForm>;
  function Probe() { latest = useQQAccountForm({ roleId: "mira", client, onChanged: () => undefined, onCleanupError: () => undefined }); return null; }
  const view = await mountTestComponent(<Probe />);
  try {
    assert.equal(latest.error?.message, "QQ 账号设置读取失败");
    assert.match(latest.error?.detail ?? "", /settings read failed/);
  } finally { await view.cleanup(); }
});
