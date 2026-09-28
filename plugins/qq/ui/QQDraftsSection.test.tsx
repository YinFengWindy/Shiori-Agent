import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { QQDraftsSection } from "./QQDraftsSection";

test("the add flow lists only this role's QQ drafts, editable and removable", async () => {
  const draft = { ws_uri: "", expected_uin: "", verified: false, auto_connect: false, connection: "offline", error: "" };
  let drafts = [
    { ...draft, ref: "draft-1", ws_uri: "ws://localhost:3001", role_id: "mira" },
    { ...draft, ref: "draft-2", ws_uri: "ws://localhost:3002", role_id: "other" },
  ];
  const calls: string[] = [];
  const client = {
    ...createPluginRpcClient("qq"),
    async call<T>(method: string): Promise<T> {
      calls.push(method);
      if (method === "accounts.settings") return { accounts: drafts } as T;
      if (method === "accounts.remove_draft") { drafts = drafts.filter((row) => row.ref !== "draft-1"); return { ok: true } as T; }
      throw new Error(method);
    },
  };
  const view = await mountTestComponent(null);
  try {
    await view.render(<QQDraftsSection roleId="mira" client={client} host={desktopPluginHostServices} onChanged={() => undefined}
      Editor={({ draftRef, roleId }) => <div>Editor for {draftRef || "new"} of {roleId}</div>} />);
    assert.match(view.container.textContent ?? "", /ws:\/\/localhost:3001/);
    assert.doesNotMatch(view.container.textContent ?? "", /ws:\/\/localhost:3002/);
    assert.match(view.container.textContent ?? "", /Editor for new of mira/);
    const button = (label: string) => Array.from(view.container.querySelectorAll("button"))
      .find((item) => item.textContent?.includes(label));
    await act(async () => { button("编辑")?.click(); });
    assert.match(view.container.textContent ?? "", /Editor for draft-1 of mira/);
    await act(async () => { button("移除")?.click(); });
    assert.equal(view.container.textContent?.includes("ws://localhost:3001"), false);
    assert.match(view.container.textContent ?? "", /Editor for new of mira/);
    assert.ok(calls.includes("accounts.remove_draft"));
  } finally { await view.cleanup(); }
});
