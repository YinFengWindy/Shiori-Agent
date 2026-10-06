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
