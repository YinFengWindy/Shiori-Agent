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

function createSurface(window: FakeCaptureWindow) {
  let resolveReady!: () => void;
  const ready = new Promise<void>((resolve) => {
    resolveReady = resolve;
  });
  return {
    createWindow: () => ({ window, ready }) as never,
    resolveReady,
  };
}

test("cancelling before the capture page loads rejects start and never reopens the microphone", async () => {
  const window = new FakeCaptureWindow();
  const surface = createSurface(window);
  const recorder = new BrowserVoiceRecorder(surface.createWindow);

  const start = recorder.start("microphone-a");
  await recorder.cancel();
  surface.resolveReady();

  await assert.rejects(start, /麦克风采集已取消/);
  assert.deepEqual(window.commands, [{ channel: "desktop:voice-capture-command", command: "cancel" }]);
});

test("accepts the renderer's sanitized audio-input device contract", async () => {
  const window = new FakeCaptureWindow();
  const surface = createSurface(window);
  const recorder = new BrowserVoiceRecorder(surface.createWindow);

  const devices = recorder.listInputDevices();
  surface.resolveReady();
  await new Promise<void>((resolve) => setImmediate(resolve));
  recorder.handleInputDevices(window.webContents as never, [{ deviceId: "microphone-a", label: "USB Mic" }]);

  assert.deepEqual(await devices, [{ deviceId: "microphone-a", label: "USB Mic" }]);
});

test("rejects a second capture while the first start is pending", async () => {
  const window = new FakeCaptureWindow();
  const surface = createSurface(window);
  const recorder = new BrowserVoiceRecorder(surface.createWindow);

  const first = recorder.start("microphone-a");
  await assert.rejects(recorder.start("microphone-b"), /已有麦克风采集/);
  await recorder.cancel();
  surface.resolveReady();
  await assert.rejects(first, /麦克风采集已取消/);
});

test("coalesces concurrent stop callers onto one renderer command", async () => {
  const window = new FakeCaptureWindow();
  const surface = createSurface(window);
  const recorder = new BrowserVoiceRecorder(surface.createWindow);

  const started = recorder.start();
  surface.resolveReady();
  await new Promise<void>((resolve) => setImmediate(resolve));
  recorder.handleReady(window.webContents as never);
  await started;

  const first = recorder.stop();
  const second = recorder.stop();
  recorder.handleStopped(window.webContents as never);

  assert.deepEqual(await first, await second);
  assert.equal(window.commands.filter((entry) => (
    entry as { channel?: unknown; command?: unknown }
  ).command === "stop").length, 1);
});
