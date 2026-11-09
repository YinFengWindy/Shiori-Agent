import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import { NativeAudioPlayer } from "./audioPlayer";

test("stopping before native window readiness settles playback and never plays its late buffer", async () => {
  const window = new EventEmitter() as EventEmitter & { isDestroyed(): boolean; webContents: EventEmitter & { send(channel: string, command: unknown): void }; destroy(): void };
  const commands: unknown[] = []; let ready!: () => void;
  window.isDestroyed = () => false; window.destroy = () => { window.emit("closed"); };
  window.webContents = Object.assign(new EventEmitter(), { send: (_channel: string, command: unknown) => { commands.push(command); } });
  const player = new NativeAudioPlayer(() => ({ window, ready: new Promise<void>((resolve) => { ready = resolve; }) }) as never);
  const playing = player.play({ audio_base64: "AQ==", format: "wav" });
  player.stop(); await playing;
  ready(); await Promise.resolve();
  assert.deepEqual(commands, [{ command: "cancel" }]);
  player.dispose();
});

test("playback observations require the actual sender, start receipt and current playback", async () => {
  const window = new EventEmitter() as EventEmitter & { isDestroyed(): boolean; webContents: EventEmitter & { send(channel: string, command: unknown): void }; destroy(): void };
  let id = "";
  window.isDestroyed = () => false; window.destroy = () => window.emit("closed");
  window.webContents = Object.assign(new EventEmitter(), { send: (_channel: string, command: { id?: string }) => { if (command.id) id = command.id; } });
  const observations: import("./audioPlayer").PlaybackObservation[] = [];
  const player = new NativeAudioPlayer(() => ({ window, ready: Promise.resolve() }) as never);
  const playing = player.play({ audio_base64: "AQ==", format: "wav" }, (value) => observations.push(value));
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  player.observe({} as never, id);
  player.observe(window.webContents as never, id, .9);
  assert.deepEqual(observations, [], "loading and unauthenticated start cannot open the mouth");
  player.observe(window.webContents as never, id);
  player.observe(window.webContents as never, id, .5);
  player.observe(window.webContents as never, id, NaN);
  player.stop(); await playing;
  player.observe(window.webContents as never, id, .9);
  assert.deepEqual(observations.map(({ phase, amplitude }) => [phase, amplitude]), [["started", 0], ["level", .5], ["ended", 0]]);
  const oldId = id;
  const successor = player.play({ audio_base64: "AQ==", format: "wav" }, (value) => observations.push(value));
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  player.observe(window.webContents as never, oldId);
  assert.equal(observations.length, 3);
  player.observe(window.webContents as never, id);
  player.finish(window.webContents as never, id, "decode failed");
  await assert.rejects(successor, /decode failed/);
  assert.deepEqual(observations.at(-1), { playback_id: id, phase: "ended", amplitude: 0, reason: "failed" });
  player.dispose();
});
