import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { deferred, mountTestComponent } from "@shiori/plugin-sdk/testing";
import { createPluginRpcTestClient, type PluginRpcTestResponder } from "../shared/testing/pluginRpcTestBridge";
import type { RoleSemanticItem } from "./roleSemanticMemory";

// Base UI binds DOM globals at import time, so the page loads inside a test window.
let RoleMemoryPage: typeof import("./RoleMemoryPage").RoleMemoryPage;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleMemoryPage } = await import("./RoleMemoryPage"));
  await environment.cleanup();
});

const windowGlobals = { miraDesktop: { onEvent: () => () => {} } };

const documents = (roleId: string) => ({ role_id: roleId, documents: [
  { name: "SELF.md", status: "ready", content: `# ${roleId} self` },
  { name: "MEMORY.md", status: "ready", content: "Long-term notes" },
  { name: "HISTORY.md", status: "error", content: "", error: "denied" },
  { name: "RECENT_CONTEXT.md", status: "empty", content: "" },
] });

const ready = (roleId: string, items: RoleSemanticItem[], total = items.length, page = 1) => ({
  role_id: roleId, status: "ready", items, total, page, page_size: 20, filters: {},
});
const numbered = (from: number, count: number) => Array.from({ length: count }, (_, index) => ({ id: `m${from + index}`, summary: `Memory ${from + index}` }));

/** Answers documents normally and delegates semantic reads to the test. */
function responder(semantic: PluginRpcTestResponder): PluginRpcTestResponder {
  return (name, params, pluginId) => name === "roles.memory.documents" ? documents(String(params.role_id)) : semantic(name, params, pluginId);
}

const text = (container: HTMLElement) => container.textContent ?? "";
const button = (container: HTMLElement, label: string) => Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((element) => element.textContent === label || element.getAttribute("aria-label") === label);
const click = async (element: HTMLElement | null | undefined) => {
  assert.ok(element, "missing element");
  await act(async () => element.click());
};

it("opens on the timeline in one navigation row and reads documents from the same row", async () => {
  const { client, calls } = createPluginRpcTestClient("default_memory", responder(() => ready("mira", numbered(1, 1))));
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

it("refreshes documents and the timeline together, back at the first batch", async () => {
  const { client, calls } = createPluginRpcTestClient("default_memory", responder((_name, params) => {
    const page = Number(params.page);
    return ready("mira", page === 1 ? numbered(1, 20) : numbered(21, 5), 25, page);
  }));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    await click(button(view.container, "加载更多"));
    assert.equal(view.container.querySelectorAll("li").length, 25);
    await click(button(view.container, "刷新记忆"));
    assert.deepEqual(calls.map((call) => [call.name, call.params.page]).sort(), [
      ["roles.memory.documents", undefined],
      ["roles.memory.documents", undefined],
      ["roles.memory.semantic.list", 1],
      ["roles.memory.semantic.list", 1],
      ["roles.memory.semantic.list", 2],
    ]);
    assert.equal(view.container.querySelectorAll("li").length, 20);
  } finally {
    await view.cleanup();
  }
});

it("keeps documents readable when the semantic layer fails or is disabled", async () => {
  let semantic: PluginRpcTestResponder = () => { throw new Error("engine offline"); };
  const { client } = createPluginRpcTestClient("default_memory", responder((...args) => semantic(...args)));
  const view = await mountTestComponent(<RoleMemoryPage client={client} roleId="mira" />, { windowGlobals });
  try {
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /读取失败/);
    await click(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]')[1]);
    assert.match(text(view.container), /mira self/);
    semantic = () => ({ role_id: "mira", status: "disabled", items: [], total: 0 });
    await click(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]')[0]);
    await click(button(view.container, "刷新记忆"));
    assert.match(text(view.container), /语义记忆已停用/);
    assert.equal(view.container.querySelector('[aria-label="搜索记忆"]'), null);
  } finally {
    await view.cleanup();
  }
});

it("drops list and detail responses that arrive after a role switch", async () => {
  const pendingList = deferred<Record<string, unknown>>();
  const pendingDetail = deferred<Record<string, unknown>>();
  let miraLists = 0;
  const { client } = createPluginRpcTestClient("default_memory", responder((name, params) => {
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
