import assert from "node:assert/strict";
import test from "node:test";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import type { PetReplyBubble } from "../shared/replyBubble";
import { ReplyBubbleController } from "./replyBubble";

const event = (roleId: string, text: string): BridgeEvent => ({
  id: "reply", type: "event", method: "chat.done", payload: { role_id: roleId, reply: text },
});

test("only the bound visible role can show a reply and binding changes clear it", () => {
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.handleEvent(event("mira", "hidden"));
  assert.equal(states.length, 0);
  bubbles.bind("mira");
  bubbles.handleEvent(event("other", "wrong role"));
  assert.equal(states.at(-1)?.text, "");
  bubbles.handleEvent(event("mira", " 普通回复 "));
  assert.equal(states.at(-1)?.text, "普通回复");
  bubbles.bind("mira");
  assert.equal(states.at(-1)?.text, "普通回复", "position saves and restores preserve the active reply");
  bubbles.bind("other");
  assert.equal(states.at(-1)?.text, "");
  bubbles.bind("");
  bubbles.handleEvent(event("other", "hidden again"));
  assert.equal(states.at(-1)?.text, "");
  bubbles.dispose();
});

test("replacement replies receive a full five seconds and lock messages wait for dismissal", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  bubbles.handleEvent(event("mira", "first"));
  t.mock.timers.tick(4_000);
  bubbles.handleEvent(event("mira", "second"));
  t.mock.timers.tick(1_000);
  assert.equal(states.at(-1)?.text, "second");
  t.mock.timers.tick(4_000);
  assert.equal(states.at(-1)?.text, "");
  bubbles.setLocked(true);
  t.mock.timers.tick(30_000);
  assert.deepEqual(states.at(-1), { text: "Windows 已锁定", paused: true, persistent: true });
  bubbles.dismiss();
  assert.deepEqual(states.at(-1), { text: "", paused: true, persistent: false });
  bubbles.setLocked(false);
  assert.deepEqual(states.at(-1), { text: "", paused: false, persistent: false });
  bubbles.dispose();
});

test("disable reclaims expiry and late queued callbacks cannot publish", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  bubbles.handleEvent(event("mira", "last"));
  bubbles.dispose();
  const count = states.length;
  t.mock.timers.tick(10_000);
  bubbles.handleEvent(event("mira", "late"));
  bubbles.bind("mira");
  bubbles.setLocked(true);
  bubbles.dismiss();
  assert.equal(states.length, count);
});

test("a held reply outlives the chat expiry and only its owner can end or clear it", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  const live = { source: "live" as const };
  assert.equal(bubbles.show(live, "other", "wrong role", null), false);
  assert.equal(bubbles.show(live, "mira", "直播回复", null), true);
  t.mock.timers.tick(60_000);
  assert.equal(states.at(-1)?.text, "直播回复", "held while its speech lasts");
  bubbles.clear("chat");
  assert.equal(states.at(-1)?.text, "直播回复", "cancelling chat leaves the live bubble");
  bubbles.release(live, null);
  assert.equal(states.at(-1)?.text, "");
  bubbles.dispose();
});

test("a newer reply takes the slot, so the older owner's release and clear are no-ops", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  const live = { source: "live" as const };
  bubbles.show(live, "mira", "直播回复", null);
  bubbles.handleEvent(event("mira", "聊天回复"));
  bubbles.release(live, null);
  bubbles.clear("live");
  assert.equal(states.at(-1)?.text, "聊天回复");
  const failed = { source: "live" as const };
  bubbles.show(failed, "mira", "朗读失败的回复", null);
  bubbles.release(failed, 3_000);
  t.mock.timers.tick(2_999);
  assert.equal(states.at(-1)?.text, "朗读失败的回复");
  t.mock.timers.tick(1);
  assert.equal(states.at(-1)?.text, "", "falls back to a timed expiry");
  bubbles.dispose();
});
