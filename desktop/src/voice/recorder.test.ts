import assert from "node:assert/strict";
import test from "node:test";
import { EventEmitter } from "node:events";
import { BrowserVoiceRecorder } from "./recorder.js";

class FakeCaptureWindow extends EventEmitter {
  readonly commands: unknown[] = [];
  readonly webContents = new EventEmitter() as EventEmitter & {
    send(channel: string, command: unknown): void;
  };

  destroyed = false;

  constructor() {
    super();
    this.webContents.send = (channel, command) => {
      this.commands.push({ channel, command });
    };
  }

  isDestroyed(): boolean {
    return this.destroyed;
  }

  destroy(): void {
    this.destroyed = true;
    this.emit("closed");
  }
}

test("cancelling before the capture page loads rejects start and never reopens the microphone", async () => {
  const window = new FakeCaptureWindow();
  const recorder = new BrowserVoiceRecorder(() => window as never);

  const start = recorder.start("microphone-a");
  await recorder.cancel();
  window.webContents.emit("did-finish-load");

  await assert.rejects(start, /麦克风采集已取消/);
  assert.deepEqual(window.commands, [{ channel: "desktop:voice-capture-command", command: "cancel" }]);
});

test("accepts the renderer's sanitized audio-input device contract", async () => {
  const window = new FakeCaptureWindow();
  const recorder = new BrowserVoiceRecorder(() => window as never);

  const devices = recorder.listInputDevices();
  window.webContents.emit("did-finish-load");
  await new Promise<void>((resolve) => setImmediate(resolve));
  recorder.handleInputDevices(window.webContents as never, [{ deviceId: "microphone-a", label: "USB Mic" }]);

  assert.deepEqual(await devices, [{ deviceId: "microphone-a", label: "USB Mic" }]);
});
