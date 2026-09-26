import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { RoleMemoryDocumentsView } from "./RoleMemoryDocumentsView";

it("shows five read-only documents, their distinct states, and refresh", async () => {
  let refreshes = 0;
  const view = await mountTestComponent(<RoleMemoryDocumentsView roleId="mira" bridgeReady loading={false} error="" onRefresh={() => { refreshes += 1; }} documents={[
    { name: "SELF.md", status: "ready", content: "# Mira" },
    { name: "MEMORY.md", status: "empty", content: "" },
    { name: "HISTORY.md", status: "missing", content: "" },
    { name: "RECENT_CONTEXT.md", status: "error", content: "", error: "denied" },
    { name: "PENDING.md", status: "ready", content: "# Pending" },
  ]} />);
  try {
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    assert.equal(tabs.length, 5);
    assert.match(view.container.textContent ?? "", /Mira/);
    await act(async () => tabs[1].click());
    assert.match(view.container.textContent ?? "", /文档为空/);
    await act(async () => tabs[2].click());
    assert.match(view.container.textContent ?? "", /文档缺失/);
    await act(async () => tabs[3].click());
    assert.match(view.container.textContent ?? "", /读取失败：denied/);
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新记忆"]')?.click());
    assert.equal(refreshes, 1);
  } finally {
    await view.cleanup();
  }
});

it("distinguishes a request failure from an individual document failure", async () => {
  const view = await mountTestComponent(<RoleMemoryDocumentsView roleId="mira" bridgeReady loading={false} error="bridge offline" documents={[]} onRefresh={() => undefined} />);
  try {
    assert.match(view.container.textContent ?? "", /读取失败：bridge offline/);
    assert.doesNotMatch(view.container.textContent ?? "", /文档缺失/);
  } finally {
    await view.cleanup();
  }
});
