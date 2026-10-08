import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import type { AffectionHistoryEntry } from "./affectionHistory";

// Base UI binds DOM globals at import time, so the panel loads inside a test window.
let RoleAffectionPanel: typeof import("./RoleAffectionPanel").RoleAffectionPanel;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleAffectionPanel } = await import("./RoleAffectionPanel"));
  await environment.cleanup();
});

const turn = (minute: number): AffectionHistoryEntry => ({
  id: minute, time: `2026-10-08T12:${String(minute).padStart(2, "0")}:00+08:00`, before: 30 + minute - 1, after: 30 + minute, delta: 1, reason: `第${minute}轮`, source: "turn",
});
const init: AffectionHistoryEntry = { id: 0, time: "2026-10-08T12:00:00+08:00", before: null, after: 30, delta: null, reason: "老朋友", source: "init" };
// Newest first, as the bridge stores and pages it: 21 turns, then init.
const history = [...Array.from({ length: 21 }, (_, index) => turn(21 - index)), init];

// The stage guidance editor below the history reads its own method.
const stagePrompts = { role_id: "mira", stages: [
  { stage: "厌恶", prompt: "冷言冷语。", default: "冷言冷语。", overridden: false },
  { stage: "陌生", prompt: "客气。", default: "客气。", overridden: false },
] };

async function mountPanel(respond: (payload: Record<string, unknown>) => Record<string, unknown>) {
  const calls: Array<Record<string, unknown>> = [];
  const invoke: DesktopInvoke = async ({ method, payload }) => {
    if (method !== "roles.affection.history") return { id: "test", type: "response", method, error: null, payload: stagePrompts };
    calls.push({ method, ...payload });
    return { id: "test", type: "response", method, error: null, payload: respond(payload) };
  };
  const view = await mountTestComponent(<RoleAffectionPanel roleId="mira" bridgeReady invoke={invoke} />, {
    windowGlobals: { miraDesktop: { onEvent: () => () => {} } },
  });
  return { view, calls };
}

const loadMore = (container: HTMLElement) => Array.from(container.querySelectorAll("button")).find((element) => element.textContent === "加载更多");

it("shows the meter and pages the history newest first down to the init entry, with no control over the value", async () => {
  const { view, calls } = await mountPanel(({ page }) => {
    const start = (Number(page) - 1) * 20;
    return { role_id: "mira", affection: { value: 51, stage: "朋友", progress: 11 / 19, floor: 40 }, items: history.slice(start, start + 20), total: history.length, page, page_size: 20 };
  });
  try {
    const meter = view.container.querySelector('[data-testid="role-affection-meter"]');
    assert.match(meter?.textContent ?? "", /^51朋友/);
    // The value and the floor sit at their places on the whole -100–100 track, in the highlighted stage.
    const left = (testId: string) => meter?.querySelector<HTMLElement>(`[data-testid="${testId}"]`)?.style.left;
    assert.equal(left("affection-track-marker"), "75.5%");
    assert.equal(left("affection-track-floor"), "70%");
    assert.equal(meter?.querySelectorAll('[data-current="true"]').length, 1);
    const changes = () => Array.from(view.container.querySelectorAll('[data-testid="affection-change"]')).map((element) => element.textContent);
    assert.equal(changes().length, 20);
    assert.equal(changes()[0], "+1");

    await act(async () => loadMore(view.container)?.click());
    assert.deepEqual(calls.map((call) => call.page), [1, 2]);
    assert.deepEqual(changes().slice(-2), ["+1", "30"]);
    assert.match(view.container.textContent ?? "", /老朋友/);
    assert.equal(loadMore(view.container), undefined);
    // The value and history are read-only: no field and no button but paging.
    const history = view.container.querySelector('[data-testid="role-affection-panel"]');
    assert.ok(history);
    assert.equal(history.querySelectorAll("input, textarea, select, [contenteditable]").length, 0);
    assert.equal(history.querySelectorAll("button").length, 0);
  } finally {
    await view.cleanup();
  }
});

it("merges consecutive decay entries into one row and has no floor marker without a floor", async () => {
  const decay = (id: number, day: number): AffectionHistoryEntry => ({
    id, time: `2026-10-0${day}T12:00:00+08:00`, before: 11 - id, after: 10 - id, delta: -1, reason: "长时间没有联系", source: "decay",
  });
  const items = [decay(3, 8), decay(2, 7), decay(1, 6), { ...init, after: 11, time: "2026-10-02T12:00:00+08:00" }];
  const { view } = await mountPanel(({ page }) => ({ role_id: "mira", affection: { value: 7, stage: "陌生", progress: 7 / 19, floor: null }, items, total: items.length, page, page_size: 20 }));
  try {
    const changes = Array.from(view.container.querySelectorAll('[data-testid="affection-change"]')).map((element) => element.textContent);
    assert.deepEqual(changes, ["-3", "11"]);
    assert.match(view.container.textContent ?? "", /长时间没有联系×3/);
    assert.equal(view.container.querySelector('[data-testid="affection-track-floor"]'), null);
  } finally {
    await view.cleanup();
  }
});

it("shows the empty state for an uninitialized role, with its stage guidance still editable", async () => {
  const { view } = await mountPanel(({ page }) => ({ role_id: "mira", affection: null, items: [], total: 0, page, page_size: 20 }));
  try {
    assert.ok(view.container.querySelector('[data-testid="role-affection-empty"]'));
    assert.equal(view.container.querySelector('[data-testid="role-affection-meter"]'), null);
    assert.equal(view.container.querySelector<HTMLTextAreaElement>('[data-testid="affection-stage-prompts"] textarea')?.value, "客气。");
    assert.equal(view.container.querySelector('[role="tab"][aria-selected="true"]')?.textContent, "陌生");
  } finally {
    await view.cleanup();
  }
});
