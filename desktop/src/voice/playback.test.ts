import assert from "node:assert/strict";
import test from "node:test";
import { BrowserVoicePlayback, type VoicePlaybackItem } from "./playback.js";

function createWindow(ready: Promise<void> = Promise.resolve()) {
  const sent: unknown[] = [];
  const webContents = {
    send: (_channel: string, value: unknown) => sent.push(value),
  };
  const window = {
    webContents,
    isDestroyed: () => false,
    destroy: () => undefined,
    once: () => undefined,
  };
  return { surface: { window, ready }, sent, webContents };
}

function item(sequence: number, turnId = "turn"): VoicePlaybackItem {
  return {
    id: `${turnId}:${sequence}`,
    turnId,
    sessionKey: "role:mira",
    requestId: turnId,
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
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: (current, next) => finished.push([current.id, next?.id ?? null]),
    onError: () => undefined,
    onDrained: () => drained.push(1),
  });

  playback.beginTurn("turn");
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

test("finishes the current sentence then continues only with the new turn", async () => {
  const surface = createWindow();
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: () => undefined,
    onDrained: () => undefined,
  });

  playback.beginTurn("old");
  playback.enqueue(item(0, "old"));
  await Promise.resolve();
  await Promise.resolve();

  playback.beginTurn("new");
  playback.enqueue(item(1, "old"));
  playback.enqueue(item(0, "new"));
  assert.equal(playback.handleFinished(surface.webContents as never, "old:0"), true);
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(surface.sent, [
    { command: "play", id: "old:0", audioBase64: "AA==", format: "mp3" },
    { command: "play", id: "new:0", audioBase64: "AA==", format: "mp3" },
  ]);
  assert.equal(playback.handleFinished(surface.webContents as never, "old:1"), false);
});

test("ignores playback completion from an unrelated renderer", async () => {
  const surface = createWindow();
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: () => undefined,
    onDrained: () => undefined,
  });
  playback.beginTurn("turn");
  playback.enqueue(item(0));
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(playback.handleFinished({} as never, "turn:0"), false);
  assert.equal(playback.handleFinished(surface.webContents as never, "unknown"), false);
});

test("waits for producer completion before draining a temporarily empty queue", async () => {
  const surface = createWindow();
  const drained: string[] = [];
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: () => undefined,
    onDrained: (turnId) => drained.push(turnId),
  });

  playback.beginTurn("turn");
  playback.enqueue(item(0));
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(playback.handleFinished(surface.webContents as never, "turn:0"), true);
  assert.deepEqual(drained, []);

  playback.enqueue(item(1));
  await Promise.resolve();
  await Promise.resolve();
  playback.finishTurn("turn");
  assert.deepEqual(drained, []);

  assert.equal(playback.handleFinished(surface.webContents as never, "turn:1"), true);
  assert.deepEqual(drained, ["turn"]);
});

test("reports old-turn playback errors without draining the active turn", async () => {
  const surface = createWindow();
  const errors: string[] = [];
  const drained: string[] = [];
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: (failed) => errors.push(failed.turnId),
    onDrained: (turnId) => drained.push(turnId),
  });

  playback.beginTurn("old");
  playback.enqueue(item(0, "old"));
  await Promise.resolve();
  await Promise.resolve();

  playback.beginTurn("new");
  playback.enqueue(item(0, "new"));
  playback.finishTurn("new");
  assert.equal(playback.handleError(surface.webContents as never, "old:0", "failed"), true);
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(errors, ["old"]);
  assert.deepEqual(drained, []);
  assert.equal(playback.handleFinished(surface.webContents as never, "new:0"), true);
  assert.deepEqual(drained, ["new"]);
});

test("plays when the hidden window finished loading before the queue started waiting", async () => {
  const surface = createWindow(Promise.resolve());
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: () => undefined,
    onDrained: () => undefined,
  });

  playback.beginTurn("turn");
  playback.enqueue(item(0));
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(surface.sent, [
    { command: "play", id: "turn:0", audioBase64: "AA==", format: "mp3" },
  ]);
});

test("reports a hidden window load failure instead of hanging the playback queue", async () => {
  const surface = createWindow(Promise.reject(new Error("语音窗口加载失败")));
  const errors: string[] = [];
  const playback = new BrowserVoicePlayback(() => surface.surface as never, {
    onStarted: () => undefined,
    onFinished: () => undefined,
    onError: (_item, message) => errors.push(message),
    onDrained: () => undefined,
  });

  playback.beginTurn("turn");
  playback.enqueue(item(0));
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(surface.sent, []);
  assert.deepEqual(errors, ["语音窗口加载失败"]);
});
