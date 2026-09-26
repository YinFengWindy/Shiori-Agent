import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { QQAccountDetail } from "./index";

test("QQ detail saves a draft before explicitly connecting it", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> | undefined }> = [];
  const changed: string[] = [];
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true, accounts: [] } as T;
      if (method === "accounts.save") return { ref: "draft-1" } as T;
      if (method === "accounts.connect") return { account_id: "account-1" } as T;
      throw new Error(method);
    },
  };
  const view = await mountTestComponent(null);
  try {
    await view.render(<QQAccountDetail account={null} onChanged={(id) => changed.push(id ?? "")}
      client={client} host={desktopPluginHostServices} />);
    const uri = view.container.querySelector<HTMLInputElement>('input[type="url"]');
    assert.ok(uri);
    await changeInputValue(uri, "ws://localhost:3001");
    const button = (label: string) => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.trim() === label);
    assert.equal(button("连接")?.disabled, true);
    await act(async () => { button("保存")?.click(); });
    assert.deepEqual(calls.map(({ method }) => method), ["accounts.settings", "accounts.save"]);
    assert.equal(changed.length, 0);
    assert.equal(button("连接")?.disabled, false);
    await act(async () => { button("连接")?.click(); });
    assert.deepEqual(calls.map(({ method }) => method), ["accounts.settings", "accounts.save", "accounts.connect"]);
    assert.deepEqual(changed, ["account-1"]);
  } finally { await view.cleanup(); }
});

test("QQ managed mode saves without an external endpoint and starts independently", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> | undefined }> = [];
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string, payload?: Record<string, unknown>): Promise<T> {
      calls.push({ method, payload });
      if (method === "accounts.settings") return { managed_available: true, accounts: [] } as T;
      if (method === "accounts.save") return { ref: "a".repeat(32) } as T;
      if (method === "accounts.connect") return { ref: "a".repeat(32), account_id: "" } as T;
      if (method === "accounts.managed_status") return {
        preparation: { stage: "downloading", percent: 42, version: "v4.18.28" },
        login: { phase: "stopped", qrcode: "", error: "" }, connection: "offline", error: "",
      } as T;
      throw new Error(method);
    },
  };
  const view = await mountTestComponent(null);
  try {
    await view.render(<QQAccountDetail account={null} onChanged={() => undefined}
      client={client} host={desktopPluginHostServices} />);
    const button = (label: string) => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.trim() === label);
    await act(async () => { button("托管 NapCat")?.click(); });
    await act(async () => { button("保存")?.click(); });
    assert.equal(calls.find((row) => row.method === "accounts.save")?.payload?.mode, "managed");
    assert.equal(calls.find((row) => row.method === "accounts.save")?.payload?.ws_uri, "");
    await act(async () => { button("连接")?.click(); });
    assert.ok(calls.some((row) => row.method === "accounts.connect"));
  } finally { await view.cleanup(); }
});
