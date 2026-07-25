import assert from "node:assert/strict";
import test from "node:test";
import { BrowserVoicePlayback, type VoicePlaybackItem } from "./playback.js";

function createWindow() {
  const sent: unknown[] = [];
  const webContents = {
    send: (_channel: string, value: unknown) => sent.push(value),
    once: (event: string, listener: () => void) => {
      if (event === "did-finish-load") listener();
    },
  };
  const window = {
    webContents,
    isDestroyed: () => false,
    destroy: () => undefined,
    once: () => undefined,
  };
  return { window, sent, webContents };
}

function item(sequence: number): VoicePlaybackItem {
  return {
    id: `turn:${sequence}`,
    sessionKey: "role:mira",
    requestId: "turn",
    sequence,
    text: `句子 ${sequence}`,
    audioBase64: "AA==",
    format: "mp3",
  };
}

test("plays queued sentences in order and drops later items after a new input", async () => {
  const surface = createWindow();
  const finished: Array<[string, string | null]> = [];
  const drained: number[] = [];
  const playback = new BrowserVoicePlayback(() => surface.window as never, {
    onStarted: () => undefined,
    onFinished: (current, next) => finished.push([current.id, next?.id ?? null]),
    onError: () => undefined,
    onDrained: () => drained.push(1),
  });

  playback.enqueue(item(0));
  playback.enqueue(item(1));
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(surface.sent, [{ command: "play", id: "turn:0", audioBase64: "AA==", format: "mp3" }]);

  assert.equal(playback.handleStarted(surface.webContents as never, "turn:0"), true);
  playback.stopAfterCurrent();
  assert.equal(playback.handleFinished(surface.webContents as never, "turn:0"), true);
  assert.deepEqual(finished, [["turn:0", null]]);
  assert.deepEqual(drained, [1]);
  assert.equal(playback.handleFinished(surface.webContents as never, "turn:1"), false);
});

test("ignores playback completion from an unrelated renderer", async () => {
  const surface = createWindow();
  const playback = new BrowserVoicePlayback(() => surface.window as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: () => undefined,
    onDrained: () => undefined,
  });
  playback.enqueue(item(0));
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(playback.handleFinished({} as never, "turn:0"), false);
  assert.equal(playback.handleFinished(surface.webContents as never, "unknown"), false);
});
