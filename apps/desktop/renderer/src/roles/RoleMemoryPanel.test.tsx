import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleMemoryDocumentsPayload } from "../shared/types";
import { RoleMemoryPanel } from "./RoleMemoryPanel";

function response(roleId: string, content: string): RoleMemoryDocumentsPayload {
  return { role_id: roleId, documents: [
    { name: "SELF.md", status: "ready", content },
    { name: "MEMORY.md", status: "empty", content: "" },
    { name: "HISTORY.md", status: "missing", content: "" },
    { name: "RECENT_CONTEXT.md", status: "error", content: "", error: "denied" },
    { name: "PENDING.md", status: "ready", content: "# Pending" },
  ] };
}

it("shows five document states and refreshes the selected role", async () => {
  const calls: string[] = [];
  let content = "# First";
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: { invoke: async ({ payload }: { payload: { role_id: string } }) => {
      calls.push(payload.role_id);
      return { payload: response(payload.role_id, content) };
    } },
  } });
  try {
    assert.match(view.container.textContent ?? "", /First/);
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    assert.equal(tabs.length, 5);
    await act(async () => tabs[1].click());
    assert.match(view.container.textContent ?? "", /文档为空/);
    await act(async () => tabs[2].click());
    assert.match(view.container.textContent ?? "", /文档缺失/);
    await act(async () => tabs[3].click());
    assert.match(view.container.textContent ?? "", /读取失败：denied/);
    await act(async () => tabs[0].click());
    content = "# Updated";
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新记忆"]')?.click());
    assert.match(view.container.textContent ?? "", /Updated/);
    assert.deepEqual(calls, ["mira", "mira"]);
  } finally {
    await view.cleanup();
  }
});

it("ignores an old role response after switching roles and separates request failures", async () => {
  let resolveMira: ((value: { payload: RoleMemoryDocumentsPayload }) => void) | undefined;
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: { invoke: ({ payload }: { payload: { role_id: string } }) => payload.role_id === "mira"
      ? new Promise((resolve: (value: { payload: RoleMemoryDocumentsPayload }) => void) => { resolveMira = resolve; })
      : Promise.resolve({ payload: response("luna", "# Luna") }),
    },
  } });
  try {
    await view.render(<RoleMemoryPanel roleId="luna" bridgeReady />);
    assert.match(view.container.textContent ?? "", /Luna/);
    await act(async () => resolveMira?.({ payload: response("mira", "# Mira") }));
    assert.match(view.container.textContent ?? "", /Luna/);
    assert.doesNotMatch(view.container.textContent ?? "", /Mira/);
  } finally {
    await view.cleanup();
  }

  const failed = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: { invoke: async () => ({ error: { message: "offline", code: "failed" } }) },
  } });
  try {
    assert.match(failed.container.textContent ?? "", /读取失败：offline/);
  } finally {
    await failed.cleanup();
  }
});
