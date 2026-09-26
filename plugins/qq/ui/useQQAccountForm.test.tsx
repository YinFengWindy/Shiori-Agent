import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { useQQAccountForm } from "./useQQAccountForm";

test("QQ form dirty state follows the saved baseline and clears on revert", async () => {
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string): Promise<T> {
      if (method === "accounts.settings") return { account: {
        ref: "saved", ws_uri: "ws://localhost:3001", timeout_seconds: 5,
        has_token: true,
      } } as T;
      throw new Error(method);
    },
  };
  function Probe() {
    const form = useQQAccountForm({ accountId: "account-1", draftRef: "", client, onChanged: () => undefined });
    return <><input value={form.fields.uri} onChange={(event) => form.setField("uri", event.target.value)} />
      <output>{form.dirty ? "dirty" : "saved"}</output></>;
  }
  const view = await mountTestComponent(<Probe />);
  try {
    const input = view.container.querySelector("input");
    assert.ok(input);
    assert.equal(input.value, "ws://localhost:3001");
    assert.equal(view.container.querySelector("output")?.textContent, "saved");
    await changeInputValue(input, "ws://localhost:3002");
    assert.equal(view.container.querySelector("output")?.textContent, "dirty");
    await changeInputValue(input, "ws://localhost:3001");
    assert.equal(view.container.querySelector("output")?.textContent, "saved");
  } finally { await view.cleanup(); }
});
