import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { NovelAiChatImageActions, isNovelAiOutput } from "./ChatImageActions";

test("NovelAI regeneration keeps its target and deadline when the selected image changes", async () => {
  const calls: unknown[] = [];
  const updates: string[] = [];
  let finish: (value: unknown) => void = () => { throw new Error("request not started"); };
  const client: PluginRpcClient = { ...createPluginRpcClient("fixture"), call: async <T,>(method: string, payload?: Record<string, unknown>, options?: { timeoutMs?: number }) => {
    calls.push({ method, payload, options });
    return await new Promise<T>((resolve) => { finish = (value) => resolve(value as T); });
  } };
  const target = { sessionKey: "role:one", historyKey: "m:0", path: "D:\\workspace\\private_runtime\\novelai\\outputs\\one.png", messageId: "m", mediaIndex: 0, timestamp: null };
  const render = (sessionKey: string) => <NovelAiChatImageActions target={{ ...target, sessionKey }} client={client}
    onSessionUpdate={(key) => updates.push(key)} onError={(message) => { if (message) assert.fail(message); }} onNotice={() => {}} />;
  const view = await mountTestComponent(render("role:one"));
  try {
    const button = view.container.querySelector<HTMLButtonElement>("button");
    assert.ok(button);
    await act(async () => { button.click(); });
    assert.equal(button.disabled, true);
    await view.render(render("role:two"));
    assert.equal(view.container.querySelector<HTMLButtonElement>("button")?.disabled, false);
    await act(async () => finish({ session: { key: "role:one" }, message: { id: "m" } }));
    assert.deepEqual(updates, ["role:one"]);
    assert.deepEqual(calls, [{ method: "regenerateMessageMedia", payload: { session_key: "role:one", message_id: "m", media_index: 0 }, options: { timeoutMs: 300_000 } }]);
  } finally { await view.cleanup(); }
});

test("unrelated chat attachments do not offer NovelAI regeneration", () => {
  assert.equal(isNovelAiOutput("D:\\workspace\\uploads\\one.png"), false);
  assert.equal(isNovelAiOutput("/workspace/private_runtime/novelai/outputs/one.png"), true);
});
