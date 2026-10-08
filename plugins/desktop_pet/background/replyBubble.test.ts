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

const hold = { kind: "hold" } as const;

test("a held reply outlives the chat expiry and only its owner can end or clear it", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  const live = { source: "live" as const, runId: "run" };
  assert.equal(bubbles.show(live, "other", "wrong role", hold), false);
  assert.equal(bubbles.show(live, "mira", "直播回复", hold), true);
  t.mock.timers.tick(60_000);
  assert.equal(states.at(-1)?.text, "直播回复", "held while its speech lasts");
  bubbles.clear("chat");
  bubbles.clear("live", "other-run");
  assert.equal(states.at(-1)?.text, "直播回复", "other sources and runs leave the live bubble");
  bubbles.release({ source: "live", runId: "run" });
  assert.equal(states.at(-1)?.text, "直播回复", "only the same owner object can end it");
  bubbles.release(live);
  assert.equal(states.at(-1)?.text, "");
  bubbles.dispose();
});

test("a newer reply covers a held one, which returns when the newer one expires or is dismissed", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  const live = { source: "live" as const, runId: "run" };
  bubbles.show(live, "mira", "直播回复", hold);
  bubbles.handleEvent(event("mira", "聊天回复"));
  assert.equal(states.at(-1)?.text, "聊天回复");
  t.mock.timers.tick(5_000);
  assert.equal(states.at(-1)?.text, "直播回复", "still speaking, so it is shown again");
  bubbles.handleEvent(event("mira", "又一条"));
  bubbles.dismiss();
  assert.equal(states.at(-1)?.text, "直播回复");
  bubbles.handleEvent(event("mira", "最后一条"));
  bubbles.release(live);
  assert.equal(states.at(-1)?.text, "最后一条", "ending the covered reply never clears the newer one");
  t.mock.timers.tick(5_000);
  assert.equal(states.at(-1)?.text, "", "nothing held any more");
  bubbles.dispose();
});

test("an unheard reply stays readable for its fallback, and dismissing the held reply drops it", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: PetReplyBubble[] = [];
  const bubbles = new ReplyBubbleController((state) => states.push(state));
  bubbles.bind("mira");
  const failed = { source: "live" as const };
  bubbles.show(failed, "mira", "朗读失败的回复", hold);
  bubbles.releaseAfter(failed, 3_000);
  t.mock.timers.tick(2_999);
  assert.equal(states.at(-1)?.text, "朗读失败的回复");
  t.mock.timers.tick(1);
  assert.equal(states.at(-1)?.text, "");
  const live = { source: "live" as const };
  bubbles.show(live, "mira", "直播回复", hold);
  bubbles.dismiss();
  bubbles.handleEvent(event("mira", "聊天回复"));
  t.mock.timers.tick(5_000);
  assert.equal(states.at(-1)?.text, "", "the user dismissed it, so it does not come back");
  bubbles.dispose();
});
