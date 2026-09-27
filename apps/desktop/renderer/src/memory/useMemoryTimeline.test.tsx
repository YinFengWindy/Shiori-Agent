import assert from "node:assert/strict";
import { it } from "node:test";
import { act, useEffect } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { createPluginRpcTestClient, type PluginRpcTestResponder } from "../shared/testing/pluginRpcTestBridge";
import type { MemoryReadContext } from "./memoryReads";
import type { RoleSemanticFilters } from "./roleSemanticMemory";
import { useMemoryTimeline } from "./useMemoryTimeline";

const windowGlobals = { miraDesktop: { onEvent: () => () => {} } };
const filters: RoleSemanticFilters = { memory_type: ["event"], status: ["active", "superseded", "all"] };
const numbered = (from: number, count: number) => Array.from({ length: count }, (_, index) => ({ id: `m${from + index}`, summary: "" }));
const ready = (roleId: string, items: Array<{ id: string; summary: string }>, total: number, page = 1) => ({
  role_id: roleId, status: "ready", items, total, page, page_size: 20, filters,
});

type Timeline = ReturnType<typeof useMemoryTimeline>;
const latest: { current: Timeline | null } = { current: null };
function Probe({ context }: { context: MemoryReadContext }) {
  const state = useMemoryTimeline(context);
  useEffect(() => { latest.current = state; });
  return null;
}

/** The hook state after the last render. */
function timeline() {
  assert.ok(latest.current, "timeline not mounted");
  return latest.current;
}

async function mountTimeline(respond: PluginRpcTestResponder) {
  const { client, calls } = createPluginRpcTestClient("default_memory", respond);
  const context = (roleId = "mira", refreshKey = 0): MemoryReadContext => ({ client, roleId, refreshKey });
  const view = await mountTestComponent(<Probe context={context()} />, { windowGlobals });
  const pages = () => calls.map((call) => call.params.page);
  return { view, calls, pages, context };
}

it("loads more batches and restarts at the first batch, collapsed, on a query change or refresh", async () => {
  const { view, calls, pages, context } = await mountTimeline((_name, params) => {
    const page = Number(params.page);
    return ready("mira", page === 1 ? numbered(1, 20) : numbered(21, 20), 45, page);
  });
  try {
    assert.equal(timeline().list?.items.length, 20);
    assert.equal(timeline().hasMore, true);
    await act(async () => timeline().toggle("m1"));
    await act(async () => timeline().loadMore());
    assert.deepEqual(pages(), [1, 2]);
    assert.equal(timeline().list?.items.length, 40);
    assert.deepEqual(timeline().expandedIds, ["m1"]);

    await act(async () => timeline().updateQuery({ memory_type: "event" }));
    assert.deepEqual(pages(), [1, 2, 1]);
    assert.equal(calls.at(-1)?.params.memory_type, "event");
    assert.equal(timeline().list?.items.length, 20);
    assert.deepEqual(timeline().expandedIds, []);
    // Declared filters stay while the new query's list replaces the old one.
    assert.deepEqual(timeline().filters, filters);

    await act(async () => timeline().updateQuery({ memory_type: "event" }));
    assert.equal(pages().length, 3);

    await act(async () => timeline().loadMore());
    await view.render(<Probe context={context("mira", 1)} />);
    assert.deepEqual(pages(), [1, 2, 1, 2, 1]);
    assert.equal(timeline().list?.items.length, 20);
  } finally {
    await view.cleanup();
  }
});

it("retries only the failed batch and keeps the loaded ones", async () => {
  let failSecond = true;
  const { view, pages } = await mountTimeline((_name, params) => {
    const page = Number(params.page);
    if (page === 2 && failSecond) {
      failSecond = false;
      throw new Error("engine busy");
    }
    return ready("mira", page === 1 ? numbered(1, 20) : numbered(21, 3), 23, page);
  });
  try {
    await act(async () => timeline().loadMore());
    assert.equal(timeline().error, "engine busy");
    assert.equal(timeline().list?.items.length, 20);
    await act(async () => timeline().retry());
    assert.deepEqual(pages(), [1, 2, 2]);
    assert.equal(timeline().error, "");
    assert.equal(timeline().list?.items.length, 23);
    assert.equal(timeline().hasMore, false);
  } finally {
    await view.cleanup();
  }
});

it("offers no filters for a disabled engine and drops another role's declaration", async () => {
  const { view, context } = await mountTimeline((_name, params) => params.role_id === "luna"
    ? { role_id: "luna", status: "disabled", items: [], total: 0 }
    : ready("mira", [], 0));
  try {
    assert.deepEqual(timeline().filters, filters);
    await view.render(<Probe context={context("luna")} />);
    assert.equal(timeline().filters, null);
    assert.equal(timeline().hasMore, false);
  } finally {
    await view.cleanup();
  }
});
