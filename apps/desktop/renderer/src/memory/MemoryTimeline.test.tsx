import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { formatTimestamp } from "../shared/format";
import { changeInputValue, mountTestComponent, chooseSelectOption } from "@shiori/plugin-sdk/testing";
import { createPluginRpcTestClient, type PluginRpcTestResponder } from "../shared/testing/pluginRpcTestBridge";
import type { RoleSemanticFilters, RoleSemanticItem } from "./roleSemanticMemory";

// Base UI binds DOM globals at import time, so the timeline loads inside a test window.
let MemoryTimeline: typeof import("./MemoryTimeline").MemoryTimeline;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ MemoryTimeline } = await import("./MemoryTimeline"));
  await environment.cleanup();
});

const windowGlobals = { miraDesktop: { onEvent: () => () => {} } };
const fullFilters: RoleSemanticFilters = { memory_type: ["event", "preference"], memory_domain: ["taste"], status: ["active", "superseded", "all"] };

const ready = (items: RoleSemanticItem[], extra: { total?: number; page?: number; filters?: RoleSemanticFilters } = {}) => ({
  role_id: "mira", status: "ready", items, total: extra.total ?? items.length, page: extra.page ?? 1, page_size: 20, filters: extra.filters ?? fullFilters,
});
const numbered = (from: number, count: number) => Array.from({ length: count }, (_, index) => ({ id: `m${from + index}`, summary: `Memory ${from + index}` }));

async function mountTimeline(respond: PluginRpcTestResponder) {
  const { client, calls } = createPluginRpcTestClient("default_memory", respond);
  const view = await mountTestComponent(<MemoryTimeline context={{ client, roleId: "mira", refreshKey: 0 }} />, { windowGlobals });
  const listCalls = () => calls.filter((call) => call.name === "roles.memory.semantic.list").map((call) => call.params);
  return { view, calls, listCalls };
}

const text = (container: HTMLElement) => container.textContent ?? "";
const nodeCount = (container: HTMLElement) => container.querySelectorAll("li").length;
const button = (container: HTMLElement, label: string) => Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((element) => element.textContent === label);
const click = async (element: HTMLElement | null | undefined) => {
  assert.ok(element, "missing element");
  await act(async () => element.click());
};
const comboboxLabels = () => Array.from(document.querySelectorAll('[role="combobox"]')).map((element) => element.getAttribute("aria-label"));

it("shows exactly the filters each engine declares", async () => {
  const cases: Array<[RoleSemanticFilters, string[]]> = [
    [fullFilters, ["记忆类型", "记忆领域", "记忆状态", "时间排序"]],
    // Types and domains only: no status picker.
    [{ memory_type: ["event"], memory_domain: [] }, ["记忆类型", "记忆领域", "时间排序"]],
    // No declared facets: search and sort only.
    [{}, ["时间排序"]],
  ];
  for (const [filters, expected] of cases) {
    const { view } = await mountTimeline(() => ready(numbered(1, 1), { filters }));
    try {
      assert.deepEqual(comboboxLabels(), expected);
      assert.ok(view.container.querySelector('[aria-label="搜索记忆"]'));
    } finally {
      await view.cleanup();
    }
  }
});

it("appends with load more and sends search, filter, status and sort from the first batch", async () => {
  const { view, listCalls } = await mountTimeline((_name, params) => {
    const page = Number(params.page);
    return ready(page === 1 ? numbered(1, 20) : numbered(21, 5), { total: 25, page });
  });
  try {
    // Unset status: the engine's default (active only) applies.
    assert.deepEqual(listCalls(), [{ role_id: "mira", q: "", sort_order: "desc", page: 1, page_size: 20 }]);
    await click(button(view.container, "加载更多"));
    assert.equal(listCalls().at(-1)?.page, 2);
    assert.equal(nodeCount(view.container), 25);
    assert.equal(button(view.container, "加载更多"), undefined);

    await chooseSelectOption("记忆类型", "preference");
    assert.equal(nodeCount(view.container), 20);
    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="搜索记忆"]')!, "tea");
    await chooseSelectOption("记忆状态", "已失效");
    await chooseSelectOption("时间排序", "最早");
    assert.deepEqual(listCalls().at(-1), { role_id: "mira", q: "tea", sort_order: "asc", page: 1, page_size: 20, memory_type: "preference", status: "superseded" });
  } finally {
    await view.cleanup();
  }
});

it("hides load more after a short final batch or a batch that adds nothing new", async () => {
  for (const second of [numbered(21, 3), numbered(1, 20)]) {
    const { view, listCalls } = await mountTimeline((_name, params) => {
      const page = Number(params.page);
      return ready(page === 1 ? numbered(1, 20) : second, { total: 100, page });
    });
    try {
      await click(button(view.container, "加载更多"));
      assert.equal(listCalls().length, 2);
      assert.equal(button(view.container, "加载更多"), undefined);
      assert.equal(nodeCount(view.container), 20 + (second[0].id === "m1" ? 0 : second.length));
    } finally {
      await view.cleanup();
    }
  }
});

it("shows a failed batch under the loaded items and retries that same batch", async () => {
  let failures = 1;
  const { view, listCalls } = await mountTimeline((_name, params) => {
    const page = Number(params.page);
    if (page === 2 && failures-- > 0) throw new Error("engine busy");
    return ready(page === 1 ? numbered(1, 20) : numbered(21, 20), { total: 60, page });
  });
  try {
    await click(button(view.container, "加载更多"));
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /读取失败/);
    await click(button(view.container, "详情"));
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /engine busy/);
    assert.equal(nodeCount(view.container), 20);
    assert.equal(button(view.container, "加载更多"), undefined);
    await click(button(view.container, "重试"));
    assert.deepEqual(listCalls().map((call) => call.page), [1, 2, 2]);
    assert.equal(view.container.querySelector('[role="alert"]'), null);
    assert.equal(nodeCount(view.container), 40);
    assert.ok(button(view.container, "加载更多"));
  } finally {
    await view.cleanup();
  }
});

it("expands several nodes in place with Chinese labels, localized times, placeholders and superseded markers", async () => {
  const items: RoleSemanticItem[] = [
    { id: "m1", summary: "Likes jasmine tea", memory_type: "preference", status: "active", happened_at: "2026-09-02T09:00:00", created_at: "2026-09-02T01:05:00+00:00" },
    { id: "m2", summary: "", memory_type: "turn", status: "superseded", created_at: "2026-09-01T12:00:00+00:00" },
  ];
  const { view, calls } = await mountTimeline((name, params) => name === "roles.memory.semantic.list"
    ? ready(items)
    : { role_id: "mira", status: "ready", item: { ...items.find((item) => item.id === params.item_id), memory_domain: "taste", source_ref: "role:mira:1" } });
  try {
    assert.match(text(view.container), /无摘要/);
    assert.equal(view.container.querySelectorAll('[aria-label="已失效"]').length, 1);
    assert.ok(Array.from(view.container.querySelectorAll("span")).some((element) => element.textContent === "preference"));
    const nodes = Array.from(view.container.querySelectorAll<HTMLButtonElement>("li button[aria-expanded]"));
    await click(nodes[0]);
    await click(nodes[1]);
    const details = view.container.querySelectorAll('[aria-label="记忆详情"]');
    assert.equal(details.length, 2);
    assert.deepEqual(calls.filter((call) => call.name === "roles.memory.semantic.detail").map((call) => call.params), [
      { role_id: "mira", item_id: "m1" },
      { role_id: "mira", item_id: "m2" },
    ]);
    const first = details[0].textContent ?? "";
    for (const label of ["状态", "领域", "来源", "发生时间", "记录时间"]) assert.match(first, new RegExp(label));
    assert.match(first, /有效/);
    assert.match(first, /taste/);
    assert.match(first, /role:mira:1/);
    assert.ok(first.includes(formatTimestamp("2026-09-02T01:05:00+00:00")));
    assert.ok(!first.includes("2026-09-02T01:05:00"));
    assert.doesNotMatch(first, /memory_domain|source_ref|created_at/);
    assert.match(details[1].textContent ?? "", /已失效/);
    await click(nodes[0]);
    assert.equal(view.container.querySelectorAll('[aria-label="记忆详情"]').length, 1);
  } finally {
    await view.cleanup();
  }
});

it("distinguishes empty, disabled and failed timelines", async () => {
  for (const [respond, expected] of [
    [() => ready([]), /暂无记忆/],
    [() => ({ role_id: "mira", status: "disabled", items: [], total: 0 }), /语义记忆已停用/],
    [() => { throw new Error("engine offline"); }, /读取失败/],
  ] satisfies Array<[PluginRpcTestResponder, RegExp]>) {
    const { view } = await mountTimeline(respond);
    try {
      assert.match(text(view.container), expected);
    } finally {
      await view.cleanup();
    }
  }
});
