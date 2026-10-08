import assert from "node:assert/strict";
import { test } from "node:test";
import type { BackgroundCtx } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import type { PetReplyBubble } from "../../shared/replyBubble";
import { ReplyBubbleController } from "../replyBubble";
import { PetSpeechQueue } from "../voice/speechQueue";
import { registerLiveReplies } from "./register";

const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };

/** Records what the live entry registers and calls, with speech off so no audio is involved. */
async function wired() {
  const events = new Map<string, (payload: Record<string, unknown>) => void>();
  const effects = new Map<string, () => unknown>();
  const calls: Array<[string, unknown]> = []; const failures: string[] = []; const bubbles: PetReplyBubble[] = [];
  let target: ((roleId: string) => void) | null = null;
  const audio: BackgroundCtx["native"]["audio"] = { devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {}, play: async () => {}, stop: async () => {} };
  const ctx: Pick<BackgroundCtx, "events" | "rpc" | "effect" | "reportFailure"> = {
    events: { on: async (method, handler) => { events.set(method, (payload) => handler(payload, { id: "test", type: "event", method, payload })); return () => {}; } },
    rpc: createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => { calls.push([method, payload]); return {} as T; } }),
    effect: (label, dispose) => { effects.set(label, dispose); },
    reportFailure: (operation) => { failures.push(operation); },
  };
  const bubble = new ReplyBubbleController((state) => bubbles.push(state));
  bubble.bind("mira");
  await registerLiveReplies(ctx, { bubbles: bubble, speech: new PetSpeechQueue(audio), ttsProvider: () => null, watchTarget: (listener) => { target = listener; } });
  return { events, effects, calls, failures, bubbles, target: (roleId: string) => target?.(roleId) };
}

test("register routes show and cancel events, reports outcomes, follows the role and reclaims on disable", async () => {
  const f = await wired();
  assert.deepEqual([...f.events.keys()].sort(), ["live.cancel", "live.reply.show"]);
  assert.deepEqual([...f.effects.keys()], ["desktop_pet_live"]);
  f.target("mira");
  f.events.get("live.reply.show")?.({ source: "live", role_id: "mira", reply_id: "r1", run_id: "run", text: "你好" });
  await flush();
  assert.equal(f.bubbles.at(-1)?.text, "你好");
  assert.deepEqual(f.calls, [["live.reply.outcome", { reply_id: "r1", run_id: "run", bubble: { status: "succeeded" }, speech: { status: "skipped" } }]]);
  f.events.get("live.cancel")?.({ run_id: "run" });
  await flush();
  assert.equal(f.bubbles.at(-1)?.text, "", "the live bubble is cleared");
  f.events.get("live.reply.show")?.({ source: "live", role_id: "mira", reply_id: "r2", run_id: "run" });
  f.events.get("live.cancel")?.({ run_id: 3 });
  await flush();
  assert.deepEqual(f.calls.at(-1)?.[1], { reply_id: "r2", run_id: "run", bubble: { status: "failed", error: "直播回复缺少 text" }, speech: { status: "failed", error: "直播回复缺少 text" } });
  assert.deepEqual(f.failures.sort(), ["live.cancel", "live.reply"]);
  await f.effects.get("desktop_pet_live")?.();
  f.events.get("live.reply.show")?.({ source: "live", role_id: "mira", reply_id: "r3", run_id: "new", text: "停用后" });
  await flush();
  assert.equal(f.calls.length, 2, "nothing is reported after disable");
});
