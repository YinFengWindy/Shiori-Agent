import type { NativeAudio, PluginNativeApi } from "@yinfengwindy/shiori-sdk";

/** Pet-owned press threshold and recording bounds; native capture owns only hardware. */
export class PetVoiceInput {
  private epoch = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private timeout: ReturnType<typeof setTimeout> | null = null;
  private started: Promise<void> | null = null;
  private capturing = false;
  private source = "";
  constructor(private readonly audio: PluginNativeApi["audio"], private readonly options: {
    enabled(): boolean; device(): string;
    status(state: "press_pending" | "recording" | "transcribing" | "idle" | "error", message?: string): void;
    captured(audio: NativeAudio, epoch: number): Promise<void>;
    interrupt(): void;
  }) {}
  press(source: string) {
    if (!this.options.enabled() || this.source) return;
    this.source = source; const epoch = ++this.epoch;
    this.options.status("press_pending");
    this.timer = setTimeout(() => {
      this.timer = null;
      if (epoch !== this.epoch) return;
      this.options.interrupt();
      this.options.status("recording");
      this.capturing = true;
      this.started = this.audio.startCapture(this.options.device());
      void this.started.catch((error) => { if (epoch === this.epoch) this.fail(error); });
      this.timeout = setTimeout(() => { void this.release(source); }, 60_000);
    }, 300);
  }
  move(source: string) { if (this.source === source && this.timer) this.cancel(); }
  async release(source: string) {
    if (this.source !== source) return;
    this.source = "";
    if (this.timer) { clearTimeout(this.timer); this.timer = null; this.options.status("idle"); return; }
    if (this.timeout) clearTimeout(this.timeout); this.timeout = null;
    const epoch = this.epoch; const start = this.started; this.started = null;
    if (!start) return;
    try {
      await start; if (epoch !== this.epoch) return;
      this.options.status("transcribing");
      const audio = await this.audio.stopCapture(); if (epoch !== this.epoch) return;
      this.capturing = false;
      await this.options.captured(audio, epoch);
    } catch (error) { if (epoch === this.epoch) this.fail(error); }
  }
  /** Invalidates late start/stop/ASR results before releasing any native resources. */
  cancel() {
    this.epoch += 1; this.source = "";
    if (this.timer) clearTimeout(this.timer); if (this.timeout) clearTimeout(this.timeout);
    this.timer = null; this.timeout = null;
    this.started = null;
    const epoch = this.epoch;
    if (this.capturing) void this.audio.cancelCapture().catch((error) => { if (epoch === this.epoch) this.fail(error); });
    this.capturing = false;
    this.options.status("idle");
  }
  current(epoch: number) { return epoch === this.epoch; }
  private fail(error: unknown) { this.cancel(); this.options.status("error", error instanceof Error ? error.message : String(error)); }
}
