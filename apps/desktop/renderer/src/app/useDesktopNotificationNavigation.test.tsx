import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/sdk/testing";
import type { DesktopNotificationsApi, NotificationChatTarget } from "../../../src/notifications/contract";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import { useDesktopNotificationNavigation } from "./useDesktopNotificationNavigation";

async function harness({ ready = true, guarded = false, pending = null as NotificationChatTarget | null } = {}) {
  let target = pending;
  let clickListener: (() => void) | undefined;
  let pendingGuard: (() => void) | undefined;
  let openResult: boolean | Promise<boolean> = true;
  const opened: string[] = [];
  const views: unknown[] = [];
  const acknowledged: number[] = [];
  const feedback = createFeedbackRecorder();
  const api: DesktopNotificationsApi = {
    getPending: async () => target,
    acknowledge: async (id) => {
      acknowledged.push(id);
      if (target?.id === id) target = null;
    },
    onClicked: (listener) => {
      clickListener = listener;
      return () => { clickListener = undefined; };
    },
  };
  function Harness() {
    useDesktopNotificationNavigation({
      ready,
      guardNavigation: (action) => { if (guarded) pendingGuard = action; else action(); },
      openChatView: (options) => { views.push(options); },
      openRole: async (roleId) => { opened.push(roleId); return openResult; },
      feedback: feedback.reporter,
    });
    return null;
  }
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { notifications: api } });
  await view.render(<Harness />);
  return {
    view, api, opened, views, acknowledged, feedback,
    pending: () => target,
    subscribed: () => Boolean(clickListener),
    openResult: (result: boolean | Promise<boolean>) => { openResult = result; },
    setReady: async (next: boolean) => { ready = next; await view.render(<Harness />); },
    click: async (next: NotificationChatTarget) => {
      target = next;
      await act(async () => clickListener?.());
    },
    confirm: async () => { await act(async () => pendingGuard?.()); },
  };
}

test("a startup click waits for the initial role load, switches to chat and acknowledges only after open", async () => {
  const h = await harness({ ready: false, pending: { id: 1, roleId: "other" } });
  try {
    assert.deepEqual(h.opened, []);
    assert.equal(h.subscribed(), false);
    await h.setReady(true);
    assert.deepEqual(h.views, [{ recordHistory: false }]);
    assert.deepEqual(h.opened, ["other"]);
    assert.deepEqual(h.acknowledged, [1]);
    assert.equal(h.pending(), null);
  } finally { await h.view.cleanup(); }
});

test("unsaved edits defer both role and view changes; the latest clicked role wins", async () => {
  const h = await harness({ guarded: true });
  try {
    await h.click({ id: 1, roleId: "first" });
    await h.click({ id: 2, roleId: "second" });
    assert.deepEqual(h.opened, []);
    assert.deepEqual(h.views, []);
    assert.deepEqual(h.acknowledged, []);
    await h.confirm();
    assert.deepEqual(h.opened, ["second"]);
    assert.deepEqual(h.acknowledged, [2]);
  } finally { await h.view.cleanup(); }
});

test("a failed chat open retains the target and retries after bridge recovery", async () => {
  const h = await harness();
  try {
    h.openResult(false);
    await h.click({ id: 3, roleId: "mira" });
    assert.deepEqual(h.acknowledged, []);
    assert.equal(h.pending()?.roleId, "mira");
    await h.setReady(false);
    h.openResult(true);
    await h.setReady(true);
    assert.deepEqual(h.opened, ["mira", "mira"]);
    assert.deepEqual(h.acknowledged, [3]);
  } finally { await h.view.cleanup(); }
});

test("renderer teardown while opening leaves the target pending for the next renderer", async () => {
  const h = await harness();
  let finish!: (opened: boolean) => void;
  h.openResult(new Promise<boolean>((resolve) => { finish = resolve; }));
  await h.click({ id: 4, roleId: "mira" });
  await h.view.cleanup();
  finish(true);
  await Promise.resolve();
  assert.equal(h.subscribed(), false);
  assert.deepEqual(h.acknowledged, []);
  assert.equal(h.pending()?.id, 4);
  const reloaded = await harness({ pending: h.pending() });
  try {
    assert.deepEqual(reloaded.opened, ["mira"]);
    assert.deepEqual(reloaded.acknowledged, [4]);
  } finally { await reloaded.view.cleanup(); }
});

test("IPC failures report feedback and a duplicate click signal cannot open the same target twice", async () => {
  const h = await harness();
  try {
    await h.click({ id: 5, roleId: "mira" });
    await h.click({ id: 5, roleId: "mira" });
    assert.deepEqual(h.opened, ["mira"]);
    h.api.getPending = async () => { throw new Error("IPC unavailable"); };
    await h.click({ id: 6, roleId: "other" });
    assert.deepEqual(h.feedback.messages("error"), ["打开通知会话失败：IPC unavailable"]);
  } finally { await h.view.cleanup(); }
});
