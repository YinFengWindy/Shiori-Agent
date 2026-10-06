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
  let rejectReady!: (error: Error) => void;
  const ready = new Promise<void>((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });
  return {
    createWindow: () => ({ window, ready }) as never,
    resolveReady,
    rejectReady,
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

test("concurrent device enumeration shares initialization and resolves both callers from one authorized response", async () => {
  const window = new FakeCaptureWindow();
  const surface = createSurface(window);
  const recorder = new BrowserVoiceRecorder(surface.createWindow);
  const first = recorder.listInputDevices();
  const second = recorder.listInputDevices();
  assert.equal(first, second);
  surface.resolveReady();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(window.commands, [{ channel: "desktop:voice-capture-command", command: { command: "list-devices" } }]);
  assert.equal(recorder.handleInputDevices(new FakeCaptureWindow().webContents as never, []), false);
  const devices = [{ deviceId: "shared-mic", label: "USB Mic" }];
  recorder.handleInputDevices(window.webContents as never, devices);
  assert.deepEqual(await Promise.all([first, second]), [devices, devices]);
});

test("enumeration failure rejects all callers and late cleanup preserves an immediate retry", async () => {
  const window = new FakeCaptureWindow();
  const surface = createSurface(window);
  const recorder = new BrowserVoiceRecorder(surface.createWindow);
  const failures = Promise.allSettled([recorder.listInputDevices(), recorder.listInputDevices()]);
  surface.resolveReady();
  await new Promise<void>((resolve) => setImmediate(resolve));
  recorder.handleError(window.webContents as never, "device enumeration failed");
  // Retry before the failed operation's finally runs: it must not clear this one.
  const retried = Promise.all([recorder.listInputDevices(), recorder.listInputDevices()]);
  for (const failure of await failures) {
    assert.equal(failure.status, "rejected");
    if (failure.status === "rejected") assert.match(String(failure.reason), /device enumeration failed/);
  }
  await new Promise<void>((resolve) => setImmediate(resolve));
  const devices = [{ deviceId: "recovered", label: "Recovered mic" }];
  recorder.handleInputDevices(window.webContents as never, devices);
  assert.deepEqual(await retried, [devices, devices]);
  assert.equal(window.commands.length, 2);
});

test("window initialization failure rejects concurrent enumeration and a new window can retry", async () => {
  const failedWindow = new FakeCaptureWindow();
  const failedSurface = createSurface(failedWindow);
  const nextWindow = new FakeCaptureWindow();
  const nextSurface = createSurface(nextWindow);
  let attempts = 0;
  const recorder = new BrowserVoiceRecorder(() => (++attempts === 1 ? failedSurface : nextSurface).createWindow());
  const failures = Promise.allSettled([recorder.listInputDevices(), recorder.listInputDevices()]);
  failedSurface.rejectReady(new Error("load failed"));
  assert.deepEqual((await failures).map((failure) => failure.status), ["rejected", "rejected"]);
  assert.deepEqual(failedWindow.commands, []);
  const retried = recorder.listInputDevices();
  nextSurface.resolveReady();
  await new Promise<void>((resolve) => setImmediate(resolve));
  recorder.handleInputDevices(nextWindow.webContents as never, []);
  assert.deepEqual(await retried, []);
  assert.equal(attempts, 2);
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
