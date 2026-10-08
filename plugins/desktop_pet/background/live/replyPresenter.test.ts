import assert from "node:assert/strict";
import { test } from "node:test";
import { createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import type { BackgroundCtx, BridgeEvent, NativeAudio, PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import type { PetReplyBubble } from "../../shared/replyBubble";
import { ReplyBubbleController } from "../replyBubble";
import { PetSpeechQueue } from "../voice/speechQueue";
import type { LiveReplyOutcome } from "./contract";
import { LiveReplyPresenter } from "./replyPresenter";

const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
const provider = { plugin_id: "neutral", service_id: "tts" };
const show = (replyId: string, text: string, runId = "run") => ({ source: "live", role_id: "mira", reply_id: replyId, run_id: runId, text });
const chatDone = (text: string): BridgeEvent => ({ id: "reply", type: "event", method: "chat.done", payload: { role_id: "mira", reply: text } });
const summary = (outcomes: LiveReplyOutcome[]) => outcomes.map(({ reply_id, bubble, speech }) => [reply_id, bubble.status, speech.status]);

/** A real bubble slot and speech line over a host player each test ends by hand. */
function fixture() {
  const log: string[] = []; const bubbles: PetReplyBubble[] = []; const outcomes: LiveReplyOutcome[] = []; const synthesized: Array<Record<string, unknown>> = [];
  let finish: (() => void) | null = null;
  const tts: { current: PluginServiceReference | null } = { current: provider };
  const audio: BackgroundCtx["native"]["audio"] = {
    devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {},
    play: (value: NativeAudio) => { log.push(`play:${value.audio_base64}`); return new Promise<void>((resolve) => { finish = resolve; }); },
    stop: async () => { log.push("stop"); finish?.(); },
  };
  const rpc = createFakePluginClient({ services: { list: async () => ({ services: [] }), call: async <T,>(_provider: unknown, _method: string, payload?: Record<string, unknown>) => {
    synthesized.push(payload ?? {}); return { audio_base64: String(payload?.text), format: "wav" } as T;
  } } });
  const bubble = new ReplyBubbleController((state) => bubbles.push(state));
  bubble.bind("mira");
  const speech = new PetSpeechQueue(audio);
  const presenter = new LiveReplyPresenter({ bubbles: bubble, speech, rpc, ttsProvider: () => tts.current, report: async (outcome) => { outcomes.push(outcome); } });
  void presenter.bind("mira");
  const text = () => bubbles.at(-1)?.text;
  return { log, bubble, speech, presenter, outcomes, synthesized, tts, text, end: () => { finish?.(); } };
}

test("a live reply is shown and spoken, its bubble outlasts the chat expiry until speech ends, and both results are reported", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture();
  const shown = f.presenter.receive(show("r1", "大家好。"));
  await flush();
  assert.equal(f.text(), "大家好。"); assert.deepEqual(f.log, ["play:大家好。"]);
  assert.deepEqual(f.synthesized, [{ text: "大家好。", role_id: "mira", mood: "" }], "the live path reads no session mood");
  t.mock.timers.tick(30_000);
  assert.equal(f.text(), "大家好。", "still speaking, so the bubble stays");
  f.end(); await shown;
  assert.equal(f.text(), "");
  assert.deepEqual(f.outcomes, [{ reply_id: "r1", run_id: "run", bubble: { status: "succeeded" }, speech: { status: "succeeded" } }]);
});

test("consecutive live replies speak serially and each bubble waits for its own speech", async () => {
  const f = fixture();
  const first = f.presenter.receive(show("r1", "第一条。"));
  const second = f.presenter.receive(show("r2", "第二条。"));
  await flush();
  assert.deepEqual(f.log, ["play:第一条。"]); assert.equal(f.text(), "第一条。");
  f.end(); await first; await flush();
  assert.deepEqual(f.log, ["play:第一条。", "play:第二条。"]); assert.equal(f.text(), "第二条。");
  f.end(); await second;
  assert.deepEqual(summary(f.outcomes), [["r1", "succeeded", "succeeded"], ["r2", "succeeded", "succeeded"]]);
});

test("cancelling live clears only live output, and cancelling chat leaves live alone", async () => {
  const f = fixture();
  const live = f.presenter.receive(show("r1", "直播。"));
  const pending = f.presenter.receive(show("r2", "待播。"));
  const chat = f.speech.enqueue({ source: "chat" }, (job) => job.play({ audio_base64: "chat", format: "wav" }));
  await flush();
  await f.speech.cancel({ source: "chat" }); await flush();
  assert.deepEqual(f.log, ["play:直播。"]); assert.equal(f.text(), "直播。");
  f.bubble.handleEvent(chatDone("聊天回复"));
  const chatSpeech = f.speech.enqueue({ source: "chat" }, (job) => job.play({ audio_base64: "chat-2", format: "wav" }));
  await f.presenter.cancel(); await live; await pending; await flush();
  assert.equal(f.text(), "聊天回复", "the chat bubble survives a live cancel");
  assert.deepEqual(f.log, ["play:直播。", "stop", "play:chat-2"]);
  f.end(); assert.deepEqual(await chatSpeech, { status: "succeeded" });
  assert.deepEqual(await chat, { status: "cancelled" });
  assert.deepEqual(summary(f.outcomes), [["r1", "succeeded", "cancelled"], ["r2", "cancelled", "cancelled"]]);
});

test("speech availability is read at each reply's turn: turned off while queued, the reply is not synthesized", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture();
  const first = f.presenter.receive(show("r1", "有声。"));
  const second = f.presenter.receive(show("r2", "无声。"));
  await flush();
  f.tts.current = null;
  f.end(); await first; await second;
  assert.deepEqual(f.synthesized.map((request) => request.text), ["有声。"]);
  assert.equal(f.text(), "无声。");
  t.mock.timers.tick(5_000);
  assert.equal(f.text(), "", "an unspoken reply expires after the fallback");
  assert.deepEqual(summary(f.outcomes), [["r1", "succeeded", "succeeded"], ["r2", "succeeded", "skipped"]]);
});

test("a chat bubble covering a speaking live reply gives the slot back while the live speech continues", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture();
  const live = f.presenter.receive(show("r1", "还在说。"));
  await flush();
  f.bubble.handleEvent(chatDone("聊天回复"));
  assert.equal(f.text(), "聊天回复");
  t.mock.timers.tick(5_000);
  assert.equal(f.text(), "还在说。"); assert.deepEqual(f.log, ["play:还在说。"]);
  f.end(); await live;
  assert.equal(f.text(), "");
});

test("replies of a cancelled run are rejected as cancelled, and a new run still speaks", async () => {
  const f = fixture();
  const old = f.presenter.receive(show("r1", "旧。", "old")); await flush();
  await f.presenter.cancel("old"); await old;
  await f.presenter.receive(show("r2", "迟到。", "old"));
  const fresh = f.presenter.receive(show("r3", "新。", "new")); await flush();
  await f.presenter.cancel();
  await f.presenter.receive(show("r4", "也迟到。", "new"));
  await fresh;
  assert.deepEqual(f.log, ["play:旧。", "stop", "play:新。", "stop"]);
  assert.deepEqual(summary(f.outcomes).sort(), [["r1", "succeeded", "cancelled"], ["r2", "cancelled", "cancelled"], ["r3", "succeeded", "cancelled"], ["r4", "cancelled", "cancelled"]]);
});

test("every reply gets one outcome: malformed, user stop, role switch and dispose included", async () => {
  const f = fixture();
  await assert.rejects(f.presenter.receive({ source: "live", role_id: "mira", reply_id: "bad", run_id: "run" }), /text/);
  const stopped = f.presenter.receive(show("r1", "被停止。")); await flush();
  await f.speech.cancel(); await stopped;
  const switched = f.presenter.receive(show("r2", "换角色。")); await flush();
  await f.presenter.bind("other"); await switched;
  await f.presenter.receive(show("r3", "别的角色。"));
  await f.presenter.bind("mira");
  const disposed = f.presenter.receive(show("r4", "停用。")); await flush();
  await f.presenter.dispose();
  assert.deepEqual(summary(f.outcomes).at(-1), ["r4", "cancelled", "cancelled"], "answered before the plugin goes away");
  f.end(); await disposed;
  assert.deepEqual(summary(f.outcomes), [
    ["bad", "failed", "failed"], ["r1", "succeeded", "cancelled"], ["r2", "succeeded", "cancelled"], ["r3", "failed", "failed"], ["r4", "cancelled", "cancelled"],
  ]);
});
