import assert from "node:assert/strict";
import { test } from "node:test";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk/contract";
import { DesktopMessageNotifications, type MessageNotificationHost } from "./controller.js";

function harness() {
  const shown: { title: string; body: string; click: () => void }[] = [];
  const opened: string[] = [];
  const errors: unknown[] = [];
  const host: MessageNotificationHost = {
    isForeground: () => false,
    isSupported: () => true,
    show: (content, click) => { shown.push({ ...content, click }); },
    openChat: (roleId) => { opened.push(roleId); },
    onError: (error) => { errors.push(error); },
  };
  const event: BridgeEvent = {
    id: "request", type: "event", method: "session.updated",
    payload: {
      change: "message_appended", session: { key: "role:mira", metadata: { role_name: "米拉" } },
      message: { id: "assistant-1", role: "assistant", content: "hi" },
    },
  };
  return { host, shown, opened, errors, event, controller: new DesktopMessageNotifications(host) };
}

test("duplicate fan-out and primary/batch copies show exactly once, clicking opens that role", () => {
  const h = harness();
  h.event.payload.messages = [h.event.payload.message];
  h.controller.handleEvent(h.event);
  h.controller.handleEvent({ ...h.event, id: "different-listener" });
  assert.equal(h.shown.length, 1);
  h.shown[0]!.click();
  assert.deepEqual(h.opened, ["mira"]);
});

test("foreground messages stay suppressed after losing focus and new messages then notify", () => {
  const h = harness();
  h.host.isForeground = () => true;
  h.controller.handleEvent(h.event);
  h.host.isForeground = () => false;
  h.controller.handleEvent(h.event);
  assert.equal(h.shown.length, 0);
  h.event.payload.message = { id: "assistant-2", role: "assistant", content: "new" };
  h.controller.handleEvent(h.event);
  assert.equal(h.shown.length, 1);
});

test("unsupported platforms are silent and native failures cannot interrupt bridge delivery", () => {
  const h = harness();
  h.host.isSupported = () => false;
  h.controller.handleEvent(h.event);
  assert.equal(h.shown.length, 0);
  const failure = new Error("native failed");
  h.host.isSupported = () => true;
  h.host.show = () => { throw failure; };
  h.event.payload.message = { id: "assistant-2", role: "assistant", content: "new" };
  assert.doesNotThrow(() => h.controller.handleEvent(h.event));
  assert.deepEqual(h.errors, [failure]);
});

test("notification click failures are logged at the boundary", () => {
  const h = harness();
  const failure = new Error("window failed");
  h.host.openChat = () => { throw failure; };
  h.controller.handleEvent(h.event);
  assert.doesNotThrow(() => h.shown[0]!.click());
  assert.deepEqual(h.errors, [failure]);
});
