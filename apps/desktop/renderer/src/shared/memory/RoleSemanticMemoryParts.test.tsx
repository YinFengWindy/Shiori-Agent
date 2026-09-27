import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act, useState } from "react";
import { changeInputValue, mountTestComponent } from "../testing/domTestHarness";
import { chooseSelectOption } from "../testing/selectTestActions";
import { initialSemanticQuery, type RoleSemanticFilters, type RoleSemanticList, type RoleSemanticQuery } from "./roleSemanticMemory";

// Base UI binds DOM globals at import time, so the pane loads inside a test window.
let RoleSemanticMemoryPane: typeof import("./RoleSemanticMemoryParts").RoleSemanticMemoryPane;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleSemanticMemoryPane } = await import("./RoleSemanticMemoryParts"));
  await environment.cleanup();
});

const readyList = (filters: RoleSemanticFilters): RoleSemanticList => ({
  role_id: "mira", status: "ready", items: [{ id: "m1", summary: "Tea", status: "active" }], total: 41, page: 1, page_size: 20, filters,
});

function renderPane(filters: RoleSemanticFilters | null, list: RoleSemanticList | null) {
  return <RoleSemanticMemoryPane query={initialSemanticQuery} onQuery={() => {}} filters={filters} list={list} loading={false} error="" selectedId="" onSelect={() => {}} detail={null} detailLoading={false} detailError="" renderError={(error) => <p role="alert">{error}</p>} />;
}

function selectLabels() {
  return Array.from(document.querySelectorAll('[role="combobox"]')).map((element) => element.getAttribute("aria-label"));
}

it("searches, filters with declared values, sorts, pages, and opens a read-only detail", async () => {
  let current: RoleSemanticQuery = initialSemanticQuery;
  const filters: RoleSemanticFilters = { memory_type: ["event", "preference"], memory_domain: ["taste"], status: ["active", "superseded", "all"] };
  function Harness() {
    const [query, setQuery] = useState(initialSemanticQuery);
    const [selectedId, setSelectedId] = useState("");
    current = query;
    return <RoleSemanticMemoryPane query={query} onQuery={setQuery} filters={filters} list={readyList(filters)} loading={false} error="" selectedId={selectedId} onSelect={setSelectedId} detail={selectedId ? { id: "m1", summary: "Tea", source_ref: "role:mira:1", extra_json: { role_id: "mira", category: "taste" } } : null} detailLoading={false} detailError="" renderError={(error) => <p role="alert">{error}</p>} />;
  }
  const view = await mountTestComponent(<Harness />);
  try {
    assert.deepEqual(selectLabels(), ["记忆类型", "记忆领域", "记忆状态", "时间排序"]);
    assert.equal(view.container.querySelector('input[aria-label="记忆类型"]'), null);
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="下一页"]')?.click());
    assert.equal(current.page, 2);
    const search = view.container.querySelector<HTMLInputElement>('[aria-label="搜索语义记忆"]');
    assert.ok(search);
    await changeInputValue(search, "Tea");
    assert.equal(current.q, "Tea");
    assert.equal(current.page, 1);
    await chooseSelectOption("记忆类型", "preference");
    assert.equal(current.memory_type, "preference");
    await chooseSelectOption("记忆领域", "taste");
    assert.equal(current.memory_domain, "taste");
    await chooseSelectOption("记忆类型", "全部类型");
    assert.equal(current.memory_type, "");
    await chooseSelectOption("记忆状态", "已失效");
    assert.equal(current.status, "superseded");
    await chooseSelectOption("时间排序", "最早");
    assert.equal(current.sort_order, "asc");
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="查看记忆 m1"]')?.click());
    assert.match(view.container.textContent ?? "", /role:mira:1/);
    assert.match(view.container.textContent ?? "", /taste/);
    assert.doesNotMatch(view.container.textContent ?? "", /role_id/);
    assert.equal(view.container.querySelector('[aria-label="记忆详情"] input'), null);
  } finally {
    await view.cleanup();
  }
});

it("shows only search and sort when the engine declares no structured filters", async () => {
  const view = await mountTestComponent(renderPane({}, readyList({})));
  try {
    assert.deepEqual(selectLabels(), ["时间排序"]);
    assert.ok(view.container.querySelector('[aria-label="搜索语义记忆"]'));
  } finally {
    await view.cleanup();
  }
});

it("hides the status filter when an engine declares types and domains only", async () => {
  const filters: RoleSemanticFilters = { memory_type: ["event"], memory_domain: [] };
  const view = await mountTestComponent(renderPane(filters, readyList(filters)));
  try {
    assert.deepEqual(selectLabels(), ["记忆类型", "记忆领域", "时间排序"]);
  } finally {
    await view.cleanup();
  }
});

it("keeps structured filters hidden before any declaration and for a disabled engine", async () => {
  const view = await mountTestComponent(renderPane(null, { role_id: "mira", status: "disabled", items: [], total: 0 }));
  try {
    assert.match(view.container.textContent ?? "", /语义记忆已停用/);
    assert.deepEqual(selectLabels(), ["时间排序"]);
  } finally {
    await view.cleanup();
  }
});
