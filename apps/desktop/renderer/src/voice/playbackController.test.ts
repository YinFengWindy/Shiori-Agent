import assert from "node:assert/strict";
import test from "node:test";
import { ensurePlaybackContextRunning, VoicePlaybackRenderer } from "./playbackController";

test("resumes a suspended hidden playback context", async () => {
  const context = {
    state: "suspended" as AudioContextState,
    async resume() {
      this.state = "running";
    },
  };

  await ensurePlaybackContextRunning(context);

  assert.equal(context.state, "running");
});

test("fails instead of hanging when autoplay keeps playback suspended", async () => {
  const context = {
    state: "suspended" as AudioContextState,
    resume: () => new Promise<void>(() => undefined),
  };

  await assert.rejects(
    ensurePlaybackContextRunning(context, 1),
    /自动播放策略阻止/,
  );
});

test("output RMS starts after decoding and follows silence, end and cancellation without another source", async (t) => {
  const events: unknown[][] = [];
  let resolveDecode!: (value: object) => void;
  let decode = new Promise<object>((resolve) => { resolveDecode = resolve; });
  const source = { buffer: null, onended: null as (() => void) | null, connect() {}, disconnect() {}, start() { events.push(["source-start"]); }, stop() { events.push(["source-stop"]); } };
  let amplitude = .25; let sourceCount = 0;
  const analyser = { fftSize: 1024, connect() {}, disconnect() {}, getFloatTimeDomainData(samples: Float32Array) { samples.fill(amplitude); } };
  class Context {
    state = "running"; destination = {};
    resume = async () => {};
    decodeAudioData = () => decode;
    createBufferSource = () => { sourceCount++; return source; };
    createAnalyser = () => analyser;
  }
  for (const [name, value] of Object.entries({ AudioContext: Context, window: { miraDesktop: {
    voicePlaybackStarted: (id: string) => events.push(["started", id]),
    voicePlaybackLevel: (id: string, value: number) => events.push(["level", id, value]),
    voicePlaybackFinished: (id: string) => events.push(["ended", id]),
    voicePlaybackError: (id: string) => events.push(["error", id]),
  } } })) {
    const previous = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { value, configurable: true });
    t.after(() => { if (previous) Object.defineProperty(globalThis, name, previous); else Reflect.deleteProperty(globalThis, name); });
  }
  t.mock.timers.enable({ apis: ["setInterval"] });
  const player = new VoicePlaybackRenderer();
  const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  player.handleCommand({ command: "play", id: "first", audioBase64: "AQ==", format: "wav" });
  t.mock.timers.tick(100); assert.deepEqual(events, []);
  resolveDecode({}); await flush();
  assert.deepEqual(events, [["source-start"], ["started", "first"]]);
  t.mock.timers.tick(33); assert.deepEqual(events.at(-1), ["level", "first", .25]);
  amplitude = 0; t.mock.timers.tick(33); assert.deepEqual(events.at(-1), ["level", "first", 0]);
  source.onended?.(); const count = events.length; t.mock.timers.tick(200);
  assert.equal(events.length, count); assert.deepEqual(events.at(-1), ["ended", "first"]);
  decode = new Promise<object>((resolve) => { resolveDecode = resolve; });
  player.handleCommand({ command: "play", id: "cancelled", audioBase64: "AQ==", format: "wav" });
  player.handleCommand({ command: "cancel" }); resolveDecode({}); await flush(); t.mock.timers.tick(100);
  assert.equal(sourceCount, 1, "cancelled decoding cannot create a source or a meter");
});
