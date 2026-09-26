import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { QQDraftsSection } from "./QQDraftsSection";

test("saved QQ drafts remain editable and removable in plugin settings", async () => {
  let drafts = [{ ref: "draft-1", ws_uri: "ws://localhost:3001", expected_uin: "", verified: false, auto_connect: false, connection: "offline", error: "" }];
  const calls: string[] = [];
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string): Promise<T> {
      calls.push(method);
      if (method === "accounts.settings") return { accounts: drafts } as T;
      if (method === "accounts.remove_draft") { drafts = []; return { ok: true } as T; }
      throw new Error(method);
    },
  };
  const view = await mountTestComponent(null);
  try {
    await view.render(<QQDraftsSection subsectionId="qq" client={client} host={desktopPluginHostServices}
      Editor={({ draftRef }) => <div>Editor for {draftRef}</div>} />);
    assert.match(view.container.textContent ?? "", /ws:\/\/localhost:3001/);
    const button = (label: string) => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.includes(label));
    await act(async () => { button("编辑")?.click(); });
    assert.match(view.container.textContent ?? "", /Editor for draft-1/);
    await act(async () => { button("移除")?.click(); });
    assert.equal(view.container.textContent?.includes("ws://localhost:3001"), false);
    assert.ok(calls.includes("accounts.remove_draft"));
  } finally { await view.cleanup(); }
});

test("legacy migration draft cannot be removed while old config can recreate it", async () => {
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string): Promise<T> {
      if (method === "accounts.settings") return { accounts: [{
        ref: "legacy", ws_uri: "ws://localhost:3001", expected_uin: "101",
        verified: false, auto_connect: false, connection: "offline", error: "",
      }] } as T;
      throw new Error(method);
    },
  };
  const view = await mountTestComponent(null);
  try {
    await view.render(<QQDraftsSection subsectionId="qq" client={client} host={desktopPluginHostServices}
      Editor={() => null} />);
    assert.match(view.container.textContent ?? "", /101/);
    assert.equal(view.container.textContent?.includes("编辑"), true);
    assert.equal(view.container.textContent?.includes("移除"), false);
  } finally { await view.cleanup(); }
});
