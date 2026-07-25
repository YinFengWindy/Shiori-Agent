import type { BrowserWindow, WebContents } from "electron";
import type { VoicePlaybackCommand } from "../shared.js";
import { createDeferred, type Deferred } from "./deferred.js";

/** One complete synthesized sentence owned by a specific voice turn. */
export type VoicePlaybackItem = {
  id: string;
  turnId: string;
  sessionKey: string;
  requestId: string;
  sequence: number;
  text: string;
  audioBase64: string;
  format: "mp3";
};

type VoicePlaybackWindowFactory = () => BrowserWindow;

export type VoicePlaybackCallbacks = {
  onStarted(item: VoicePlaybackItem): void;
  onFinished(item: VoicePlaybackItem, nextItem: VoicePlaybackItem | null): void;
  onError(item: VoicePlaybackItem, message: string): void;
  onDrained(turnId: string): void;
};

/** Queues complete MP3 sentences and owns the hidden renderer playback surface. */
export class BrowserVoicePlayback {
  private window: BrowserWindow | null = null;
  private ready: Deferred<void> | null = null;
  private queue: VoicePlaybackItem[] = [];
  private current: VoicePlaybackItem | null = null;
  private pumping = false;
  private activeTurnId = "";
  private activeTurnFinished = false;
  private activeTurnDrained = false;
  private stoppedTurnId = "";

  constructor(
    private readonly createWindow: VoicePlaybackWindowFactory,
    private readonly callbacks: VoicePlaybackCallbacks,
  ) {}

  /** Selects the only turn whose newly arriving audio may enter the queue. */
  beginTurn(turnId: string): void {
    const nextTurnId = turnId.trim();
    if (!nextTurnId || nextTurnId === this.activeTurnId) return;
    this.activeTurnId = nextTurnId;
    this.activeTurnFinished = false;
    this.activeTurnDrained = false;
    this.stoppedTurnId = "";
    this.queue = [];
  }

  /** Adds an audio sentence while preserving bridge sequence order. */
  enqueue(item: VoicePlaybackItem): void {
    if (!item.id || !item.audioBase64 || item.turnId !== this.activeTurnId) return;
    this.queue.push(item);
    void this.pump();
  }

  /** Marks backend synthesis complete so an empty queue can end the turn. */
  finishTurn(turnId: string): void {
    if (!turnId || turnId !== this.activeTurnId) return;
    this.activeTurnFinished = true;
    this.notifyActiveTurnDrained();
  }

  /** Drops queued sentences while allowing the currently playing sentence to finish. */
  stopAfterCurrent(): void {
    const stoppedTurnId = this.activeTurnId;
    this.activeTurnId = "";
    this.activeTurnFinished = false;
    this.activeTurnDrained = false;
    this.queue = [];
    if (this.current) {
      this.stoppedTurnId = stoppedTurnId;
      return;
    }
    if (stoppedTurnId) this.callbacks.onDrained(stoppedTurnId);
  }

  /** Cancels playback during app teardown and releases the hidden renderer. */
  dispose(): void {
    this.queue = [];
    this.current = null;
    this.activeTurnId = "";
    this.activeTurnFinished = false;
    this.activeTurnDrained = false;
    this.stoppedTurnId = "";
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
    const next = this.queue[0] ?? null;
    this.current = null;
    this.callbacks.onFinished(completed, next);
    if (!next) {
      if (this.stoppedTurnId === completed.turnId) {
        this.callbacks.onDrained(this.stoppedTurnId);
        this.stoppedTurnId = "";
      }
      this.notifyActiveTurnDrained();
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
    if (this.queue.length === 0) {
      if (this.stoppedTurnId === failed.turnId) {
        this.callbacks.onDrained(this.stoppedTurnId);
        this.stoppedTurnId = "";
      }
      this.notifyActiveTurnDrained();
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
    this.ready = createDeferred<void>();
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

  private notifyActiveTurnDrained(): void {
    if (
      !this.activeTurnId
      || !this.activeTurnFinished
      || this.activeTurnDrained
      || this.queue.length > 0
      || this.current?.turnId === this.activeTurnId
    ) {
      return;
    }
    this.activeTurnDrained = true;
    this.callbacks.onDrained(this.activeTurnId);
  }

  private isPlaybackSender(sender: WebContents): boolean {
    return Boolean(this.window && !this.window.isDestroyed() && sender === this.window.webContents);
  }
}
