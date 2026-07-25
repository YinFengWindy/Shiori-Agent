import type { BrowserWindow, WebContents } from "electron";
import { encodeVoiceWav } from "./wav.js";
import type { VoiceRecorder } from "./controller.js";
import type { VoiceCaptureCommand } from "../shared.js";

type Deferred<T> = {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: Error): void;
};

/** Creates a one-shot promise used for the hidden capture page handshake. */
function deferred<T>(): Deferred<T> {
  let resolvePromise!: (value: T) => void;
  let rejectPromise!: (error: Error) => void;
  const promise = new Promise<T>((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}

type VoiceCaptureWindowFactory = () => BrowserWindow;

/** Owns the hidden capture renderer and converts its samples to an ASR WAV. */
export class BrowserVoiceRecorder implements VoiceRecorder {
  private window: BrowserWindow | null = null;
  private ready: Deferred<void> | null = null;
  private started: Deferred<void> | null = null;
  private stopped: Deferred<Uint8Array> | null = null;
  private sampleChunks: Int16Array[] = [];

  constructor(private readonly createWindow: VoiceCaptureWindowFactory) {}

  async start(): Promise<void> {
    const window = this.ensureWindow();
    await this.waitUntilReady(window);
    this.sampleChunks = [];
    this.started = deferred<void>();
    this.sendCommand("start");
    await this.started.promise;
    this.started = null;
  }

  async stop(): Promise<Uint8Array> {
    if (!this.window || this.window.isDestroyed()) {
      throw new Error("麦克风采集窗口不可用");
    }
    this.stopped = deferred<Uint8Array>();
    this.sendCommand("stop");
    const audio = await this.stopped.promise;
    this.stopped = null;
    return audio;
  }

  async cancel(): Promise<void> {
    if (!this.window || this.window.isDestroyed()) return;
    this.sendCommand("cancel");
    this.sampleChunks = [];
    this.started = null;
    this.stopped = null;
  }

  /** Accepts a readiness signal from the authorized hidden capture renderer. */
  handleReady(sender: WebContents): boolean {
    if (!this.isCaptureSender(sender)) return false;
    this.started?.resolve(undefined);
    return true;
  }

  /** Accepts one PCM chunk without retaining it beyond this recording. */
  handleData(sender: WebContents, samples: ArrayBuffer): boolean {
    if (!this.isCaptureSender(sender)) return false;
    if (samples.byteLength % 2 !== 0) {
      this.handleError(sender, "麦克风返回了无效的 PCM 数据");
      return true;
    }
    this.sampleChunks.push(new Int16Array(samples.slice(0)));
    return true;
  }

  /** Finishes one recording and resolves the encoded WAV bytes. */
  handleStopped(sender: WebContents): boolean {
    if (!this.isCaptureSender(sender)) return false;
    const length = this.sampleChunks.reduce((total, chunk) => total + chunk.length, 0);
    const samples = new Int16Array(length);
    let offset = 0;
    for (const chunk of this.sampleChunks) {
      samples.set(chunk, offset);
      offset += chunk.length;
    }
    this.sampleChunks = [];
    this.stopped?.resolve(encodeVoiceWav(samples));
    return true;
  }

  /** Fails the active recorder operation with a user-safe microphone message. */
  handleError(sender: WebContents, message: string): boolean {
    if (!this.isCaptureSender(sender)) return false;
    const error = new Error(message || "麦克风采集失败");
    this.started?.reject(error);
    this.stopped?.reject(error);
    this.started = null;
    this.stopped = null;
    this.sampleChunks = [];
    return true;
  }

  /** Releases the hidden renderer and every in-flight capture promise. */
  dispose(): void {
    this.sampleChunks = [];
    this.started?.reject(new Error("麦克风采集已关闭"));
    this.stopped?.reject(new Error("麦克风采集已关闭"));
    this.started = null;
    this.stopped = null;
    this.ready?.reject(new Error("麦克风采集已关闭"));
    this.ready = null;
    this.window?.destroy();
    this.window = null;
  }

  private ensureWindow(): BrowserWindow {
    if (this.window && !this.window.isDestroyed()) return this.window;
    const window = this.createWindow();
    this.window = window;
    this.ready = deferred<void>();
    window.webContents.once("did-finish-load", () => this.ready?.resolve(undefined));
    window.once("closed", () => {
      if (this.window !== window) return;
      this.window = null;
      this.ready = null;
    });
    return window;
  }

  private async waitUntilReady(window: BrowserWindow): Promise<void> {
    if (window.isDestroyed()) throw new Error("麦克风采集窗口不可用");
    await this.ready?.promise;
  }

  private sendCommand(command: VoiceCaptureCommand): void {
    if (!this.window || this.window.isDestroyed()) throw new Error("麦克风采集窗口不可用");
    this.window.webContents.send("desktop:voice-capture-command", command);
  }

  private isCaptureSender(sender: WebContents): boolean {
    return Boolean(this.window && !this.window.isDestroyed() && sender === this.window.webContents);
  }
}
