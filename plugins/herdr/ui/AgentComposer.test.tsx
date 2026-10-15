import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { AgentComposer } from "./AgentComposer";
import { makeCommand } from "./testFixtures";
import type { AgentCommandResponse } from "./types";

test("the draft goes to the agent as a prompt and clears; a failure keeps it and shows why", async () => {
  const fake = createFakeHostServices();
  const request = deferred<AgentCommandResponse>();
  const calls: unknown[] = [];
  let sent = 0;
  let answer: () => Promise<AgentCommandResponse> = () => request.promise;
  const client = createFakePluginClient({ call: async <T,>(name: string, payload?: Record<string, unknown>) => { calls.push({ name, payload }); return await answer() as T; } });
  const view = await mountTestComponent(<AgentComposer direct={{ paneId: "wR:p2", enabled: true, onSent: () => { sent += 1; } }} client={client} host={fake.host} />);
  try {
    const input = view.container.querySelector<HTMLTextAreaElement>('textarea[aria-label="发给 Agent"]');
    assert.ok(input);
    await changeInputValue(input, "继续\n第二行");
    await act(async () => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    assert.deepEqual(calls, [{ name: "agents.prompt", payload: { pane_id: "wR:p2", text: "继续\n第二行" } }]);
    await act(async () => request.resolve({ command: makeCommand() }));
    assert.equal(input.value, "");
    assert.equal(sent, 1);

    // A timeout is reported, never resent, and the text stays for the user to decide.
    answer = () => Promise.reject(new Error("未确认 Agent 收到；输入可能已经送达，未自动重发。"));
    await changeInputValue(input, "再来一次");
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="发送"]')?.click());
    assert.match(view.container.textContent ?? "", /可能已经送达/);
    assert.equal(input.value, "再来一次");
    assert.equal(calls.length, 2);
    assert.equal(sent, 2);
  } finally { await view.cleanup(); }
});

test("the input and interrupt are disabled while the agent cannot take input", async () => {
  const fake = createFakeHostServices();
  const view = await mountTestComponent(<AgentComposer direct={{ paneId: "wR:p2", enabled: false, onSent: () => {} }} client={createFakePluginClient()} host={fake.host} />);
  try {
    assert.equal(view.container.querySelector("textarea")?.disabled, true);
    assert.equal(view.container.querySelector<HTMLButtonElement>('button[aria-label="中断"]')?.disabled, true);
  } finally { await view.cleanup(); }
});
