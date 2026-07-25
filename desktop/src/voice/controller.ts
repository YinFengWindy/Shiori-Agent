import type { BridgeResponse, VoiceStatePayload } from "../shared.js";
import {
  VOICE_MAX_RECORDING_MS,
  VOICE_PRESS_THRESHOLD_MS,
  createVoiceInteractionState,
  transitionVoiceInteraction,
  type VoiceInputSource,
  type VoiceInteractionEvent,
  type VoiceInteractionState,
} from "./interactionState.js";

/** Supplies short PCM/WAV recordings to the desktop voice controller. */
export interface VoiceRecorder {
  start(): Promise<void>;
  stop(): Promise<Uint8Array>;
  cancel(): Promise<void>;
}

/** The small bridge surface needed to run ASR and reuse the existing chat Loop. */
export interface VoiceBridge {
  invoke(request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse>;
}

export type DesktopVoiceControllerOptions = {
  recorder: VoiceRecorder;
  bridge: VoiceBridge;
  isEnabled: () => boolean;
  roleId: () => string | null;
  publishState: (payload: VoiceStatePayload) => void;
  now?: () => number;
  schedule?: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearSchedule?: (timer: ReturnType<typeof setTimeout>) => void;
};

/** Coordinates one desktop voice turn while keeping device/provider details injectable. */
export class DesktopVoiceController {
  private state: VoiceInteractionState = createVoiceInteractionState();
  private readonly now: () => number;
  private readonly schedule: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  private readonly clearSchedule: (timer: ReturnType<typeof setTimeout>) => void;
  private pressTimer: ReturnType<typeof setTimeout> | null = null;
  private recordingTimer: ReturnType<typeof setTimeout> | null = null;
  private recordingStart: Promise<void> | null = null;
  private disposed = false;

  constructor(private readonly options: DesktopVoiceControllerOptions) {
    this.now = options.now ?? Date.now;
    this.schedule = options.schedule ?? setTimeout;
    this.clearSchedule = options.clearSchedule ?? clearTimeout;
  }

  /** Returns the state currently shown by the pet and other desktop surfaces. */
  get currentState(): VoiceInteractionState {
    return this.state;
  }

  /** Starts the shared press-pending phase for a pet or global-hotkey input. */
  startPress(source: VoiceInputSource, atMs = this.now()): boolean {
    if (this.disposed || !this.options.isEnabled()) return false;
    if (this.state.kind === "error") this.apply({ type: "reset" });
    if (this.state.kind !== "idle") return false;
    this.apply({ type: "press_started", source, atMs });
    this.clearPressTimer();
    this.pressTimer = this.schedule(() => {
      this.pressTimer = null;
      if (!this.options.isEnabled() || this.state.kind !== "press_pending") return;
      this.apply({ type: "press_elapsed", atMs: this.now() });
      if (this.currentState.kind === "recording") this.beginRecording();
    }, VOICE_PRESS_THRESHOLD_MS);
    return true;
  }

  /** Lets the pet drag recognizer win before the voice threshold expires. */
  pointerMoved(): void {
    if (this.state.kind !== "press_pending") return;
    this.clearPressTimer();
    this.apply({ type: "pointer_moved" });
  }

  /** Finishes a pending press or submits the current recording for ASR. */
  release(): void {
    if (this.state.kind === "press_pending") {
      this.clearPressTimer();
      this.apply({ type: "released" });
      return;
    }
    if (this.state.kind !== "recording") return;
    this.clearRecordingTimer();
    this.apply({ type: "released" });
    void this.finishRecording();
  }

  /** Cancels the current recording without contacting ASR or the chat Loop. */
  cancel(): void {
    this.clearPressTimer();
    this.clearRecordingTimer();
    if (this.state.kind === "recording") {
      void this.options.recorder.cancel();
    }
    if (this.state.kind !== "idle") this.apply({ type: "escape" });
  }

  /** Cancels timers and releases the recorder during app or pet shutdown. */
  dispose(): void {
    this.disposed = true;
    this.clearPressTimer();
    this.clearRecordingTimer();
    if (this.state.kind === "recording") void this.options.recorder.cancel();
    this.state = { kind: "idle" };
  }

  private beginRecording(): void {
    this.recordingStart = this.options.recorder.start().catch((error: unknown) => {
      this.apply({ type: "recording_failed", message: errorMessage(error, "没有可用的麦克风") });
    });
    this.recordingTimer = this.schedule(() => {
      this.recordingTimer = null;
      if (this.state.kind !== "recording") return;
      this.apply({ type: "recording_timed_out" });
      void this.finishRecording();
    }, VOICE_MAX_RECORDING_MS);
  }

  private async finishRecording(): Promise<void> {
    const start = this.recordingStart;
    this.recordingStart = null;
    try {
      await start;
      const audio = await this.options.recorder.stop();
      if (this.disposed || this.state.kind !== "transcribing") return;
      const transcribe = await this.options.bridge.invoke({
        method: "voice.transcribe",
        payload: { audio_base64: Buffer.from(audio).toString("base64") },
      });
      if (transcribe.error) {
        this.apply({ type: "asr_failed", message: transcribe.error.message });
        return;
      }
      const text = String(transcribe.payload.text ?? "").trim();
      this.apply({ type: "asr_succeeded", text });
      if (this.currentState.kind !== "sending") return;
      const roleId = this.options.roleId();
      if (!roleId) {
        this.apply({ type: "chat_failed", message: "当前没有可用角色" });
        return;
      }
      const chat = await this.options.bridge.invoke({
        method: "chat.send",
        payload: {
          role_id: roleId,
          content: text,
          media: [],
          input_method: "voice",
        },
      });
      if (chat.error) {
        this.apply({ type: "chat_failed", message: chat.error.message });
        return;
      }
      this.apply({ type: "chat_accepted" });
    } catch (error: unknown) {
      if (this.state.kind === "transcribing") {
        this.apply({ type: "asr_failed", message: errorMessage(error, "语音识别失败，请重试") });
      } else if (this.state.kind === "sending") {
        this.apply({ type: "chat_failed", message: errorMessage(error, "消息发送失败") });
      }
    }
  }

  private apply(event: VoiceInteractionEvent): void {
    const next = transitionVoiceInteraction(this.state, event);
    if (next === this.state) return;
    this.state = next;
    this.options.publishState(toVoiceStatePayload(next));
  }

  private clearPressTimer(): void {
    if (!this.pressTimer) return;
    this.clearSchedule(this.pressTimer);
    this.pressTimer = null;
  }

  private clearRecordingTimer(): void {
    if (!this.recordingTimer) return;
    this.clearSchedule(this.recordingTimer);
    this.recordingTimer = null;
  }
}

function toVoiceStatePayload(state: VoiceInteractionState): VoiceStatePayload {
  if (state.kind === "error") return { status: "error", message: state.message };
  return {
    status: state.kind,
    source: "source" in state ? state.source : undefined,
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
