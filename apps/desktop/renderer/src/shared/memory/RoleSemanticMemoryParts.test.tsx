import assert from "node:assert/strict";
import { it } from "node:test";
import { act, useState } from "react";
import { changeInputValue, mountTestComponent } from "../testing/domTestHarness";
import { RoleSemanticMemoryPane } from "./RoleSemanticMemoryParts";
import { initialSemanticQuery, type RoleSemanticQuery } from "./roleSemanticMemory";

it("searches, filters, pages, and opens a read-only semantic detail", async () => {
  let current: RoleSemanticQuery = initialSemanticQuery;
  function Harness() {
    const [query, setQuery] = useState(initialSemanticQuery);
    const [selectedId, setSelectedId] = useState("");
    current = query;
    return <RoleSemanticMemoryPane query={query} onQuery={setQuery} supportsStructuredFilters list={{ role_id: "mira", status: "ready", items: [{ id: "m1", summary: "Tea", status: "active" }], total: 41 }} loading={false} error="" selectedId={selectedId} onSelect={setSelectedId} detail={selectedId ? { id: "m1", summary: "Tea", source_ref: "role:mira:1", extra_json: { role_id: "mira", category: "taste" } } : null} detailLoading={false} detailError="" renderError={(error) => <p role="alert">{error}</p>} />;
  }
  const view = await mountTestComponent(<Harness />);
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="下一页"]')?.click());
    assert.equal(current.page, 2);
    const search = view.container.querySelector<HTMLInputElement>('[aria-label="搜索语义记忆"]');
    assert.ok(search);
    await changeInputValue(search, "Tea");
    assert.equal(current.q, "Tea");
    assert.equal(current.page, 1);
    await act(async () => {
      const status = view.container.querySelector<HTMLSelectElement>('[aria-label="记忆状态"]');
      if (status) { status.value = "superseded"; status.dispatchEvent(new Event("change", { bubbles: true })); }
    });
    assert.equal(current.status, "superseded");
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="查看记忆 m1"]')?.click());
    assert.match(view.container.textContent ?? "", /role:mira:1/);
    assert.match(view.container.textContent ?? "", /taste/);
    assert.doesNotMatch(view.container.textContent ?? "", /role_id/);
    assert.equal(view.container.querySelector('[aria-label="记忆详情"] input'), null);
  } finally {
    await view.cleanup();
  }
});

it("keeps Akasha's unsupported type, domain, and status filters hidden", async () => {
  const view = await mountTestComponent(<RoleSemanticMemoryPane query={initialSemanticQuery} onQuery={() => {}} supportsStructuredFilters={false} list={{ role_id: "mira", status: "disabled", items: [], total: 0 }} loading={false} error="" selectedId="" onSelect={() => {}} detail={null} detailLoading={false} detailError="" renderError={(error) => <p role="alert">{error}</p>} />);
  try {
    assert.match(view.container.textContent ?? "", /语义记忆已停用/);
    assert.equal(view.container.querySelector('[aria-label="记忆类型"]'), null);
    assert.equal(view.container.querySelector('[aria-label="记忆领域"]'), null);
    assert.equal(view.container.querySelector('[aria-label="记忆状态"]'), null);
  } finally {
    await view.cleanup();
  }
});
