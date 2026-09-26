import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { MemoryDocumentPane, MemoryDocumentTabs, MemoryRefreshButton } from "./RoleMemoryDocumentParts";

it("delegates document selection and refresh to its caller", async () => {
  let selected = "";
  let refreshes = 0;
  const view = await mountTestComponent(<div>
    <MemoryDocumentTabs selected="SELF.md" onSelect={(name) => { selected = name; }} />
    <MemoryRefreshButton disabled={false} onRefresh={() => { refreshes += 1; }} />
  </div>);
  try {
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    assert.equal(tabs.length, 5);
    await act(async () => tabs[1].click());
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新记忆"]')?.click());
    assert.equal(selected, "MEMORY.md");
    assert.equal(refreshes, 1);
  } finally {
    await view.cleanup();
  }
});

it("distinguishes ready, empty, missing, and host-rendered errors", async () => {
  const props = { name: "SELF.md" as const, roleId: "mira", bridgeReady: true, loading: false, error: "", renderError: (message: string) => <span data-testid="injected-error">{message}</span> };
  const view = await mountTestComponent(<MemoryDocumentPane {...props} document={{ name: "SELF.md", status: "ready", content: "# Mira" }} />);
  try {
    assert.match(view.container.textContent ?? "", /Mira/);
    await view.render(<MemoryDocumentPane {...props} document={{ name: "SELF.md", status: "empty", content: "" }} />);
    assert.match(view.container.textContent ?? "", /文档为空/);
    await view.render(<MemoryDocumentPane {...props} document={undefined} />);
    assert.match(view.container.textContent ?? "", /文档缺失/);
    await view.render(<MemoryDocumentPane {...props} document={{ name: "SELF.md", status: "error", content: "", error: "denied" }} />);
    assert.equal(view.container.querySelector('[data-testid="injected-error"]')?.textContent, "读取失败：denied");
    await view.render(<MemoryDocumentPane {...props} error="bridge offline" document={undefined} />);
    assert.equal(view.container.querySelector('[data-testid="injected-error"]')?.textContent, "读取失败：bridge offline");
  } finally {
    await view.cleanup();
  }
});
