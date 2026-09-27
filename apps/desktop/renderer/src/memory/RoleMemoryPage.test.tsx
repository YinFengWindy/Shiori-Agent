import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { formatTimestamp } from "../shared/format";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { chooseSelectOption } from "../shared/testing/selectTestActions";
import { createMemoryTestClient, deferred, type MemoryTestResponder } from "./memoryTestBridge";
import type { RoleSemanticFilters, RoleSemanticItem } from "./roleSemanticMemory";

// Base UI binds DOM globals at import time, so the page loads inside a test window.
let RoleMemoryPage: typeof import("./RoleMemoryPage").RoleMemoryPage;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleMemoryPage } = await import("./RoleMemoryPage"));
  await environment.cleanup();
});

const windowGlobals = { miraDesktop: { onEvent: () => () => {} } };
const fullFilters: RoleSemanticFilters = { memory_type: ["event", "preference"], memory_domain: ["taste"], status: ["active", "superseded", "all"] };

const documents = (roleId: string) => ({ role_id: roleId, documents: [
  { name: "SELF.md", status: "ready", content: `# ${roleId} self` },
  { name: "MEMORY.md", status: "ready", content: "Long-term notes" },
  { name: "HISTORY.md", status: "error", content: "", error: "denied" },
  { name: "RECENT_CONTEXT.md", status: "empty", content: "" },
] });

const ready = (roleId: string, items: RoleSemanticItem[], extra: { total?: number; page?: number; filters?: RoleSemanticFilters } = {}) => ({
  role_id: roleId, status: "ready", items, total: extra.total ?? items.length, page: extra.page ?? 1, page_size: 20, filters: extra.filters ?? fullFilters,
});

const numbered = (from: number, count: number) => Array.from({ length: count }, (_, index) => ({
  id: `m${from + index}`, summary: `Memory ${from + index}`, happened_at: "2026-09-02T09:00:00", status: "active",
}));

/** Answers documents normally and delegates semantic reads to the test. */
function responder(semantic: MemoryTestResponder): MemoryTestResponder {
  return (name, params, pluginId) => name === "roles.memory.documents" ? documents(String(params.role_id)) : semantic(name, params, pluginId);
}

const text = (container: HTMLElement) => container.textContent ?? "";
const nodeCount = (container: HTMLElement) => container.querySelectorAll("li").length;
const button = (container: HTMLElement, label: string) => Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((element) => element.textContent?.includes(label) || element.getAttribute("aria-label") === label);
const click = async (element: HTMLElement | null | undefined) => {
  assert.ok(element, "missing element");
  await act(async () => element.click());
};
const comboboxLabels = () => Array.from(document.querySelectorAll('[role="combobox"]')).map((element) => element.getAttribute("aria-label"));

it("opens on the timeline in one navigation row and reads documents from the same row", async () => {
  const { client, calls } = createMemoryTestClient("default_memory", responder(() => ready("mira", numbered(1, 1))));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    assert.deepEqual(tabs.map((tab) => tab.textContent), ["时间线", "自我", "长期", "经历", "近期", "待整理"]);
    assert.equal(tabs[0].getAttribute("aria-selected"), "true");
    // One row: the tablist, a divider between the timeline and documents, and refresh at its end.
    const tablist = view.container.querySelector('[role="tablist"]');
    assert.equal(tablist?.children[1].getAttribute("data-testid"), "memory-nav-divider");
    assert.equal(tablist?.parentElement?.lastElementChild?.getAttribute("aria-label"), "刷新记忆");
    assert.equal(view.container.querySelector("h1, h2"), null);
    assert.doesNotMatch(text(view.container), /默认记忆|Akasha/);
    assert.match(text(view.container), /Memory 1/);
    assert.deepEqual(calls.map((call) => call.name).sort(), ["roles.memory.documents", "roles.memory.semantic.list"]);

    await click(tabs[2]);
    assert.equal(tabs[2].getAttribute("aria-selected"), "true");
    assert.match(text(view.container), /Long-term notes/);
    assert.doesNotMatch(text(view.container), /Memory 1/);
    await click(tabs[3]);
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /读取失败：denied/);
    await click(tabs[4]);
    assert.match(text(view.container), /文档为空/);
    await click(tabs[5]);
    assert.match(text(view.container), /文档缺失/);
    // Switching documents reuses the one read.
    assert.equal(calls.filter((call) => call.name === "roles.memory.documents").length, 1);
  } finally {
    await view.cleanup();
  }
});

it("shows exactly the filters each engine declares", async () => {
  const cases: Array<[RoleSemanticFilters, string[]]> = [
    [fullFilters, ["记忆类型", "记忆领域", "记忆状态", "时间排序"]],
    // Types and domains only: no status picker.
    [{ memory_type: ["event"], memory_domain: [] }, ["记忆类型", "记忆领域", "时间排序"]],
    // Akasha declares nothing: search and sort only.
    [{}, ["时间排序"]],
  ];
  for (const [filters, expected] of cases) {
    const { client } = createMemoryTestClient("demo", responder(() => ready("mira", numbered(1, 1), { filters })));
    const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
    try {
      assert.deepEqual(comboboxLabels(), expected);
      assert.ok(view.container.querySelector('[aria-label="搜索记忆"]'));
    } finally {
      await view.cleanup();
    }
  }
});

it("appends with load more and restarts at the first batch on search, filter, sort and refresh", async () => {
  const { client, calls } = createMemoryTestClient("default_memory", responder((_name, params) => {
    const page = Number(params.page);
    return ready("mira", page === 1 ? numbered(1, 20) : numbered(21, 5), { total: 25, page });
  }));
  const listCalls = () => calls.filter((call) => call.name === "roles.memory.semantic.list").map((call) => call.params);
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    // Unset status: the engine's default (active only) applies.
    assert.deepEqual(listCalls(), [{ role_id: "mira", q: "", sort_order: "desc", page: 1, page_size: 20 }]);
    await click(button(view.container, "加载更多"));
    assert.equal(listCalls().at(-1)?.page, 2);
    assert.equal(nodeCount(view.container), 25);
    assert.equal(button(view.container, "加载更多"), undefined);

    await chooseSelectOption("记忆类型", "preference");
    assert.deepEqual(listCalls().at(-1), { role_id: "mira", q: "", sort_order: "desc", page: 1, page_size: 20, memory_type: "preference" });
    assert.equal(nodeCount(view.container), 20);
    assert.ok(button(view.container, "加载更多"));

    await click(button(view.container, "加载更多"));
    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="搜索记忆"]')!, "tea");
    assert.deepEqual(listCalls().at(-1), { role_id: "mira", q: "tea", sort_order: "desc", page: 1, page_size: 20, memory_type: "preference" });

    await chooseSelectOption("记忆状态", "已失效");
    assert.equal(listCalls().at(-1)?.status, "superseded");
    await chooseSelectOption("时间排序", "最早");
    assert.deepEqual(listCalls().at(-1), { role_id: "mira", q: "tea", sort_order: "asc", page: 1, page_size: 20, memory_type: "preference", status: "superseded" });

    await click(button(view.container, "加载更多"));
    assert.equal(nodeCount(view.container), 25);
    const documentReads = calls.filter((call) => call.name === "roles.memory.documents").length;
    await click(button(view.container, "刷新记忆"));
    assert.equal(listCalls().at(-1)?.page, 1);
    assert.equal(calls.filter((call) => call.name === "roles.memory.documents").length, documentReads + 1);
    assert.equal(nodeCount(view.container), 20);
  } finally {
    await view.cleanup();
  }
});

it("expands several nodes in place with Chinese labels, localized times, placeholders and superseded markers", async () => {
  const items: RoleSemanticItem[] = [
    { id: "m1", summary: "Likes jasmine tea", memory_type: "preference", status: "active", happened_at: "2026-09-02T09:00:00", created_at: "2026-09-02T01:05:00+00:00" },
    { id: "m2", summary: "", memory_type: "turn", status: "superseded", created_at: "2026-09-01T12:00:00+00:00" },
  ];
  const { client, calls } = createMemoryTestClient("default_memory", responder((name, params) => name === "roles.memory.semantic.list"
    ? ready("mira", items)
    : { role_id: "mira", status: "ready", item: { ...items.find((item) => item.id === params.item_id), memory_domain: "taste", source_ref: "role:mira:1" } }));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
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

it("distinguishes empty, disabled and failed timelines, and a failed timeline leaves documents readable", async () => {
  let semantic: MemoryTestResponder = () => ready("mira", []);
  const { client } = createMemoryTestClient("default_memory", responder((...args) => semantic(...args)));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    assert.match(text(view.container), /暂无记忆/);
    semantic = () => ({ role_id: "mira", status: "disabled", items: [], total: 0 });
    await click(button(view.container, "刷新记忆"));
    assert.match(text(view.container), /语义记忆已停用/);
    assert.equal(view.container.querySelector('[aria-label="搜索记忆"]'), null);
    semantic = () => { throw new Error("engine offline"); };
    await click(button(view.container, "刷新记忆"));
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /读取失败：engine offline/);
    await click(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]')[1]);
    assert.match(text(view.container), /mira self/);
  } finally {
    await view.cleanup();
  }
});

it("drops list and detail responses that arrive after a role switch", async () => {
  const pendingList = deferred<Record<string, unknown>>();
  const pendingDetail = deferred<Record<string, unknown>>();
  let miraLists = 0;
  const { client } = createMemoryTestClient("default_memory", responder((name, params) => {
    if (params.role_id === "atlas") return ready("atlas", [{ id: "a1", summary: "Atlas memory" }]);
    if (name === "roles.memory.semantic.detail") return pendingDetail.promise;
    // Mira's first list answers at once; her second stays in flight.
    return ++miraLists === 1 ? ready("mira", [{ id: "m1", summary: "Mira visible" }]) : pendingList.promise;
  }));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    await click(view.container.querySelector<HTMLButtonElement>("li button[aria-expanded]"));
    assert.match(text(view.container), /加载中/);
    await view.render(<RoleMemoryPage client={client} roleId="atlas" />);
    await act(async () => pendingDetail.resolve({ role_id: "mira", status: "ready", item: { id: "m1", summary: "Mira detail secret" } }));
    assert.match(text(view.container), /Atlas memory/);
    assert.equal(view.container.querySelector('[aria-label="记忆详情"]'), null);

    await view.render(<RoleMemoryPage client={client} roleId="mira" />);
    await view.render(<RoleMemoryPage client={client} roleId="atlas" />);
    await act(async () => pendingList.resolve(ready("mira", [{ id: "m9", summary: "Mira secret" }])));
    assert.match(text(view.container), /Atlas memory/);
    assert.doesNotMatch(text(view.container), /Mira/);
  } finally {
    await view.cleanup();
  }
});

it("rejects a response for a different role", async () => {
  const { client } = createMemoryTestClient("default_memory", responder(() => ready("luna", [{ id: "l1", summary: "Luna memory" }])));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /角色不匹配/);
    assert.doesNotMatch(text(view.container), /Luna memory/);
  } finally {
    await view.cleanup();
  }
});
