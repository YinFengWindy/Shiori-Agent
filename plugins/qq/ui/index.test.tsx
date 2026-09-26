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
      .find((item) => item.textContent?.includes(label));
    assert.equal(button("连接")?.disabled, true);
    await act(async () => { button("保存")?.click(); });
    assert.deepEqual(calls.map(({ method }) => method), ["accounts.save"]);
    assert.equal(changed.length, 0);
    assert.equal(button("连接")?.disabled, false);
    await act(async () => { button("连接")?.click(); });
    assert.deepEqual(calls.map(({ method }) => method), ["accounts.save", "accounts.connect"]);
    assert.deepEqual(changed, ["account-1"]);
  } finally { await view.cleanup(); }
});
