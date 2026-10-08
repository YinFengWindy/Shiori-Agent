import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { AffectionHistoryEntry } from "./affectionHistory";

// Base UI binds DOM globals at import time, so the panel loads inside a test window.
let RoleAffectionPanel: typeof import("./RoleAffectionPanel").RoleAffectionPanel;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleAffectionPanel } = await import("./RoleAffectionPanel"));
  await environment.cleanup();
});

const turn = (minute: number): AffectionHistoryEntry => ({
  time: `2026-10-08T12:${String(minute).padStart(2, "0")}:00+08:00`, before: 30 + minute - 1, after: 30 + minute, delta: 1, reason: `第${minute}轮`, source: "turn",
});
const init: AffectionHistoryEntry = { time: "2026-10-08T12:00:00+08:00", before: null, after: 30, delta: null, reason: "老朋友", source: "init" };
// Newest first, as the bridge stores and pages it: 21 turns, then init.
const history = [...Array.from({ length: 21 }, (_, index) => turn(21 - index)), init];

async function mountPanel(respond: (payload: Record<string, unknown>) => Record<string, unknown>) {
  const calls: Array<Record<string, unknown>> = [];
  const invoke = async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
    calls.push({ method, ...payload });
    return { id: "test", type: "response", method, error: null, payload: respond(payload) };
  };
  const view = await mountTestComponent(<RoleAffectionPanel roleId="mira" bridgeReady />, {
    windowGlobals: { miraDesktop: { onEvent: () => () => {}, invoke } },
  });
  return { view, calls };
}

const loadMore = (container: HTMLElement) => Array.from(container.querySelectorAll("button")).find((element) => element.textContent === "加载更多");

it("shows the meter and pages the history newest first down to the init entry, without edit controls", async () => {
  const { view, calls } = await mountPanel(({ page }) => {
    const start = (Number(page) - 1) * 20;
    return { role_id: "mira", affection: { value: 51, stage: "朋友", progress: 11 / 19 }, items: history.slice(start, start + 20), total: history.length, page, page_size: 20 };
  });
  try {
    const meter = view.container.querySelector('[data-testid="role-affection-meter"]');
    assert.match(meter?.textContent ?? "", /朋友.*51/);
    const changes = () => Array.from(view.container.querySelectorAll('[data-testid="affection-change"]')).map((element) => element.textContent);
    assert.equal(changes().length, 20);
    assert.equal(changes()[0], "+1");

    await act(async () => loadMore(view.container)?.click());
    assert.deepEqual(calls.map((call) => call.page), [1, 2]);
    assert.deepEqual(changes().slice(-2), ["+1", "30"]);
    assert.match(view.container.textContent ?? "", /老朋友/);
    assert.equal(loadMore(view.container), undefined);
    // Read-only: no field and no button but paging.
    assert.equal(view.container.querySelectorAll("input, textarea, select, [contenteditable]").length, 0);
    assert.equal(view.container.querySelectorAll("button").length, 0);
  } finally {
    await view.cleanup();
  }
});

it("shows only the empty state for an uninitialized role", async () => {
  const { view } = await mountPanel(({ page }) => ({ role_id: "mira", affection: null, items: [], total: 0, page, page_size: 20 }));
  try {
    assert.ok(view.container.querySelector('[data-testid="role-affection-empty"]'));
    assert.equal(view.container.querySelector('[data-testid="role-affection-meter"]'), null);
  } finally {
    await view.cleanup();
  }
});
