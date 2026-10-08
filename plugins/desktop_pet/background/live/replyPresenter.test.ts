import assert from "node:assert/strict";
import { test } from "node:test";
import type { BackgroundCtx, BridgeEvent, NativeAudio } from "@yinfengwindy/shiori-sdk";
import type { PetReplyBubble } from "../../shared/replyBubble";
import { ReplyBubbleController } from "../replyBubble";
import { PetSpeechQueue } from "../voice/speechQueue";
import type { LiveReplyOutcome } from "./contract";
import { LiveReplyPresenter } from "./replyPresenter";

const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
const provider = { plugin_id: "neutral", service_id: "tts" };
const reply = (replyId: string, text: string) => ({ roleId: "mira", replyId, runId: "run", text });
const chatDone = (text: string): BridgeEvent => ({ id: "reply", type: "event", method: "chat.done", payload: { role_id: "mira", reply: text } });

/** A real bubble slot and speech line over a host player each test ends by hand. */
function fixture(tts: typeof provider | null = provider) {
  const log: string[] = []; const bubbles: PetReplyBubble[] = []; const outcomes: LiveReplyOutcome[] = []; const moods: string[] = [];
  let finish: (() => void) | null = null;
  const audio: BackgroundCtx["native"]["audio"] = {
    devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {},
    play: (value: NativeAudio) => { log.push(`play:${value.audio_base64}`); return new Promise<void>((resolve) => { finish = resolve; }); },
    stop: async () => { log.push("stop"); finish?.(); },
  };
  const bubble = new ReplyBubbleController((state) => bubbles.push(state));
  bubble.bind("mira");
  const speech = new PetSpeechQueue(audio);
  const presenter = new LiveReplyPresenter({
    bubbles: bubble, speech, ttsProvider: () => tts, visibleRoleId: () => "mira",
    synthesize: async (_provider, payload) => { moods.push(payload.mood); return { audio_base64: payload.text, format: "wav" }; },
    report: async (outcome) => { outcomes.push(outcome); },
  });
  const text = () => bubbles.at(-1)?.text;
  return { log, bubble, speech, presenter, outcomes, moods, text, end: () => { finish?.(); } };
}

test("a live reply is shown and spoken, the bubble outlasts the chat expiry until speech ends, and both results are reported", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture();
  const shown = f.presenter.show(reply("r1", "大家好。"));
  await flush();
  assert.equal(f.text(), "大家好。"); assert.deepEqual(f.log, ["play:大家好。"]);
  assert.deepEqual(f.moods, [""], "the live path reads no session mood");
  t.mock.timers.tick(30_000);
  assert.equal(f.text(), "大家好。", "still speaking, so the bubble stays");
  f.end(); await shown;
  assert.equal(f.text(), "");
  assert.deepEqual(f.outcomes, [{ reply_id: "r1", run_id: "run", bubble: { status: "succeeded" }, speech: { status: "succeeded" } }]);
});

test("consecutive live replies speak serially and each bubble waits for its own speech", async () => {
  const f = fixture();
  const first = f.presenter.show(reply("r1", "第一条。"));
  const second = f.presenter.show(reply("r2", "第二条。"));
  await flush();
  assert.deepEqual(f.log, ["play:第一条。"]); assert.equal(f.text(), "第一条。");
  f.end(); await first; await flush();
  assert.deepEqual(f.log, ["play:第一条。", "play:第二条。"]); assert.equal(f.text(), "第二条。");
  f.end(); await second;
  assert.deepEqual(f.outcomes.map((outcome) => outcome.reply_id), ["r1", "r2"]);
});

test("cancelling live clears only live output, and cancelling chat leaves live alone", async () => {
  const f = fixture();
  const live = f.presenter.show(reply("r1", "直播。"));
  const pending = f.presenter.show(reply("r2", "待播。"));
  const chat = f.speech.enqueue({ source: "chat" }, (job) => job.play({ audio_base64: "chat", format: "wav" }));
  await flush();
  // Chat cancellation mid-live: live keeps its bubble and its speaker.
  await f.speech.cancel("chat"); await flush();
  assert.deepEqual(f.log, ["play:直播。"]); assert.equal(f.text(), "直播。");
  // A chat reply takes the slot; cancelling live now stops live speech but keeps the chat bubble.
  f.bubble.handleEvent(chatDone("聊天回复"));
  const chatSpeech = f.speech.enqueue({ source: "chat" }, (job) => job.play({ audio_base64: "chat-2", format: "wav" }));
  await f.presenter.cancel(); await live; await pending; await flush();
  assert.equal(f.text(), "聊天回复");
  assert.deepEqual(f.log, ["play:直播。", "stop", "play:chat-2"]);
  f.end(); assert.deepEqual(await chatSpeech, { status: "succeeded" });
  assert.deepEqual(await chat, { status: "cancelled" });
  assert.deepEqual(f.outcomes.map(({ reply_id, bubble, speech }) => [reply_id, bubble.status, speech.status]), [
    ["r1", "succeeded", "cancelled"], ["r2", "cancelled", "cancelled"],
  ]);
});

test("with speech off the bubble expires after the fallback duration and speech reports failure", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture(null);
  await f.presenter.show(reply("r1", "无声回复"));
  assert.equal(f.text(), "无声回复"); assert.deepEqual(f.log, []);
  t.mock.timers.tick(5_000);
  assert.equal(f.text(), "");
  assert.deepEqual(f.outcomes, [{ reply_id: "r1", run_id: "run", bubble: { status: "succeeded" }, speech: { status: "failed", error: "桌宠语音未开启" } }]);
});

test("a role switch retires live replies, and disposal reports nothing more", async () => {
  const f = fixture();
  await f.presenter.bind("mira");
  const live = f.presenter.show(reply("r1", "旧角色。")); await flush();
  await f.presenter.bind("other"); await live;
  assert.deepEqual(f.outcomes.map((outcome) => outcome.speech.status), ["cancelled"]);
  const late = f.presenter.show(reply("r2", "迟到。")); await flush();
  await f.presenter.dispose(); f.end(); await late;
  assert.equal(f.outcomes.length, 1);
});
