import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { InterruptButton } from "./InterruptButton";

test("one Ctrl+C per click, never a second before the first settled; a failure is reported", async () => {
  const fake = createFakeHostServices();
  const request = deferred<unknown>();
  const calls: unknown[] = [];
  let answer: () => Promise<unknown> = () => request.promise;
  const client = createFakePluginClient({ call: async <T,>(name: string, payload?: Record<string, unknown>) => { calls.push({ name, payload }); return await answer() as T; } });
  const view = await mountTestComponent(<InterruptButton paneId="wR:p2" disabled={false} client={client} host={fake.host} onSent={() => {}} />);
  try {
    const button = view.container.querySelector<HTMLButtonElement>('button[aria-label="中断"]');
    assert.ok(button);
    await act(async () => { button.click(); button.click(); });
    assert.deepEqual(calls, [{ name: "agents.keys", payload: { pane_id: "wR:p2", keys: ["ctrl+c"] } }]);
    await act(async () => request.resolve({}));

    answer = () => Promise.reject(new Error("Agent 已关闭，未发送。"));
    await act(async () => button.click());
    assert.deepEqual(fake.feedback.map((item) => [item.message, item.options?.detail]), [["中断未发送", "Agent 已关闭，未发送。"]]);
  } finally { await view.cleanup(); }
});
