import type { BrowserWindow, WebContents } from "electron";
import type { VoicePlaybackCommand } from "../shared.js";

export type VoicePlaybackItem = {
  id: string;
  sessionKey: string;
  requestId: string;
  sequence: number;
  text: string;
  audioBase64: string;
  format: "mp3";
};

type VoicePlaybackWindowFactory = () => BrowserWindow;

type VoicePlaybackCallbacks = {
  onStarted(item: VoicePlaybackItem): void;
  onFinished(item: VoicePlaybackItem, nextItem: VoicePlaybackItem | null): void;
  onError(item: VoicePlaybackItem, message: string): void;
  onDrained(): void;
};

type Deferred = {
  promise: Promise<void>;
  resolve(): void;
  reject(error: Error): void;
};

function deferred(): Deferred {
  let resolvePromise!: () => void;
  let rejectPromise!: (error: Error) => void;
  const promise = new Promise<void>((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}

/** Queues complete MP3 sentences and owns the hidden renderer playback surface. */
export class BrowserVoicePlayback {
  private window: BrowserWindow | null = null;
  private ready: Deferred | null = null;
  private queue: VoicePlaybackItem[] = [];
  private current: VoicePlaybackItem | null = null;
  private pumping = false;
  private finishCurrent = false;

  constructor(
    private readonly createWindow: VoicePlaybackWindowFactory,
    private readonly callbacks: VoicePlaybackCallbacks,
  ) {}

  /** Adds an audio sentence while preserving bridge sequence order. */
  enqueue(item: VoicePlaybackItem): void {
    if (!item.id || !item.audioBase64) return;
    this.queue.push(item);
    void this.pump();
  }

  /** Drops queued sentences while allowing the currently playing sentence to finish. */
  stopAfterCurrent(): void {
    this.queue = [];
    if (this.current) {
      this.finishCurrent = true;
      return;
    }
    this.callbacks.onDrained();
  }

  /** Cancels playback during app teardown and releases the hidden renderer. */
  dispose(): void {
    this.queue = [];
    this.current = null;
    this.finishCurrent = false;
    if (this.window && !this.window.isDestroyed()) {
      this.window.webContents.send("desktop:voice-playback-command", { command: "cancel" } satisfies VoicePlaybackCommand);
      this.window.destroy();
    }
    this.window = null;
    this.ready = null;
  }

  /** Accepts a playback-start signal only from the hidden playback renderer. */
  handleStarted(sender: WebContents, id: string): boolean {
    if (!this.isPlaybackSender(sender) || this.current?.id !== id) return false;
    this.callbacks.onStarted(this.current);
    return true;
  }

  /** Accepts a natural playback completion only for the active sentence. */
  handleFinished(sender: WebContents, id: string): boolean {
    if (!this.isPlaybackSender(sender) || this.current?.id !== id) return false;
    const completed = this.current;
    const next = this.finishCurrent ? null : (this.queue[0] ?? null);
    this.current = null;
    this.callbacks.onFinished(completed, next);
    if (this.finishCurrent || !next) {
      this.finishCurrent = false;
      if (!next) this.callbacks.onDrained();
      return true;
    }
    void this.pump();
    return true;
  }

  /** Accepts a playback error and continues with later queued sentences. */
  handleError(sender: WebContents, id: string, message: string): boolean {
    if (!this.isPlaybackSender(sender) || this.current?.id !== id) return false;
    const failed = this.current;
    this.current = null;
    this.callbacks.onError(failed, message || "音频播放失败");
    if (this.finishCurrent || this.queue.length === 0) {
      this.finishCurrent = false;
      if (this.queue.length === 0) this.callbacks.onDrained();
      return true;
    }
    void this.pump();
    return true;
  }

  private async pump(): Promise<void> {
    if (this.pumping || this.current || this.queue.length === 0) return;
    this.pumping = true;
    try {
      const window = this.ensureWindow();
      await this.ready?.promise;
      if (window.isDestroyed() || this.current || this.queue.length === 0) return;
      this.current = this.queue.shift() ?? null;
      if (!this.current) return;
      const command: VoicePlaybackCommand = {
        command: "play",
        id: this.current.id,
        audioBase64: this.current.audioBase64,
        format: this.current.format,
      };
      window.webContents.send("desktop:voice-playback-command", command);
    } finally {
      this.pumping = false;
    }
  }

  private ensureWindow(): BrowserWindow {
    if (this.window && !this.window.isDestroyed()) return this.window;
    const window = this.createWindow();
    this.window = window;
    this.ready = deferred();
    window.webContents.once("did-finish-load", () => this.ready?.resolve());
    window.once("closed", () => {
      if (this.window !== window) return;
      this.window = null;
      this.ready = null;
      this.current = null;
      this.queue = [];
    });
    return window;
  }

  private isPlaybackSender(sender: WebContents): boolean {
    return Boolean(this.window && !this.window.isDestroyed() && sender === this.window.webContents);
  }
}
