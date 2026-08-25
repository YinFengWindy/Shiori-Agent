import { randomUUID } from "node:crypto";
import type { BridgeResponse, VoiceStatePayload } from "../bridge/shared.js";
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
  start(deviceId?: string): Promise<void>;
  stop(): Promise<Uint8Array>;
  cancel(): Promise<void>;
}

/** The small bridge surface needed to run ASR and reuse the existing chat Loop. */
export interface VoiceBridge {
  invoke(request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse>;
}

/** Injected device, bridge, timing, and turn-selection dependencies. */
export type DesktopVoiceControllerOptions = {
  recorder: VoiceRecorder;
  bridge: VoiceBridge;
  isEnabled: () => boolean;
  roleId: () => string | null;
  publishState: (payload: VoiceStatePayload) => void;
  /** Selects the new turn and retires queued speech owned by the previous turn. */
  onNewInput?: (previousTurnId: string | null, nextTurnId: string) => void;
  /** Retires backend and playback work when the active reply is cancelled. */
  onCancelTurn?: (turnId: string) => void;
  microphoneDeviceId?: () => string;
  createTurnId?: () => string;
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
  private pendingReplyPress: { source: VoiceInputSource; atMs: number } | null = null;
  private recordingTimer: ReturnType<typeof setTimeout> | null = null;
  private recordingStart: Promise<void> | null = null;
  private activeTurnId: string | null = null;
  private inputOwner: VoiceInputSource | null = null;
  private operationGeneration = 0;
  private pendingTtsFailure = "";
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

  /** Returns the turn whose bridge and playback events are currently authoritative. */
  get currentTurnId(): string | null {
    return this.activeTurnId;
  }

  /** Starts the shared press-pending phase for a pet or global-hotkey input. */
  startPress(source: VoiceInputSource, atMs = this.now()): boolean {
    if (this.disposed || !this.options.isEnabled()) return false;
    if (["waiting_reply", "speaking_prepare", "speaking", "finish_current_sentence_then_idle"].includes(this.state.kind)) {
      if (this.pendingReplyPress) return false;
      this.inputOwner = source;
      this.pendingReplyPress = { source, atMs };
      this.clearPressTimer();
      this.pressTimer = this.schedule(() => this.beginReplyInterruptPress(), VOICE_PRESS_THRESHOLD_MS);
      return true;
    }
    if (this.state.kind === "error") this.apply({ type: "reset" });
    if (this.state.kind !== "idle") return false;
    this.inputOwner = source;
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
  pointerMoved(source?: VoiceInputSource): void {
    if (source && source !== this.inputOwner) return;
    if (this.pendingReplyPress) {
      this.pendingReplyPress = null;
      this.inputOwner = null;
      this.clearPressTimer();
      return;
    }
    if (this.state.kind !== "press_pending") return;
    this.clearPressTimer();
    this.apply({ type: "pointer_moved" });
  }

  /** Finishes a pending press or submits the current recording for ASR. */
  release(source?: VoiceInputSource): void {
    if (source && source !== this.inputOwner) return;
    if (this.pendingReplyPress) {
      this.pendingReplyPress = null;
      this.inputOwner = null;
      this.clearPressTimer();
      return;
    }
    if (this.state.kind === "press_pending") {
      this.clearPressTimer();
      this.inputOwner = null;
      this.apply({ type: "released" });
      return;
    }
    if (this.state.kind === "dragging") {
      this.apply({ type: "released" });
      this.inputOwner = null;
      return;
    }
    if (this.state.kind !== "recording") return;
    this.clearRecordingTimer();
    this.apply({ type: "released" });
    this.inputOwner = null;
    void this.finishRecording();
  }

  /** Cancels the current recording without contacting ASR or the chat Loop. */
  cancel(source?: VoiceInputSource): void {
    if (source && source !== this.inputOwner) return;
    const retiredTurnId = this.activeTurnId;
    this.operationGeneration += 1;
    this.pendingTtsFailure = "";
    this.pendingReplyPress = null;
    this.inputOwner = null;
    this.activeTurnId = null;
    this.clearPressTimer();
    this.clearRecordingTimer();
    if (this.state.kind === "recording" || this.state.kind === "transcribing") {
      void this.options.recorder.cancel();
    }
    if (retiredTurnId) this.options.onCancelTurn?.(retiredTurnId);
    if (this.state.kind !== "idle") this.apply({ type: "reset" });
  }

  /** Cancels timers and releases the recorder during app or pet shutdown. */
  dispose(): void {
    this.disposed = true;
    this.operationGeneration += 1;
    this.pendingTtsFailure = "";
    this.pendingReplyPress = null;
    this.clearPressTimer();
    this.clearRecordingTimer();
    if (this.state.kind === "recording" || this.state.kind === "transcribing") void this.options.recorder.cancel();
    if (this.activeTurnId) this.options.onCancelTurn?.(this.activeTurnId);
    this.activeTurnId = null;
    this.inputOwner = null;
    this.state = { kind: "idle" };
  }

  /** Advances the reply portion of the state machine when bridge text begins. */
  replyStarted(hasVoice: boolean): void {
    this.apply({ type: "reply_started", hasVoice });
  }

  /** Marks one sentence as ready for playback after its audio reaches Electron. */
  sentenceReady(sentenceId: string): void {
    if (this.state.kind === "waiting_reply") this.apply({ type: "reply_started", hasVoice: true });
    this.apply({ type: "sentence_ready", sentenceId });
  }

  /** Advances or completes the current sentence after the hidden player reports onended. */
  sentencePlaybackFinished(sentenceId: string, nextSentenceId?: string): void {
    this.apply({ type: "sentence_playback_finished", sentenceId, nextSentenceId });
  }

  /** Ends a text-only reply or finishes any audio queued before a TTS failure. */
  replyFinished(): void {
    const failure = this.pendingTtsFailure;
    this.pendingTtsFailure = "";
    this.apply({ type: "reply_finished" });
    this.activeTurnId = null;
    if (failure) this.options.publishState({ status: "error", message: failure });
  }

  /** Defers TTS failure presentation until previously queued audio has drained. */
  ttsFailed(message: string): void {
    this.pendingTtsFailure = message || "角色语音合成失败";
  }

  private beginRecording(): void {
    const generation = ++this.operationGeneration;
    this.recordingStart = this.options.recorder.start(this.options.microphoneDeviceId?.() ?? "")
      .then(() => {
        if (!this.isCurrentOperation(generation) || !["recording", "transcribing"].includes(this.state.kind)) return;
        this.pendingTtsFailure = "";
        const previousTurnId = this.activeTurnId;
        const nextTurnId = (this.options.createTurnId ?? randomUUID)();
        this.activeTurnId = nextTurnId;
        this.options.onNewInput?.(previousTurnId, nextTurnId);
      })
      .catch((error: unknown) => {
        if (!this.isCurrentOperation(generation)) return;
        this.apply({ type: "recording_failed", message: errorMessage(error, "没有可用的麦克风") });
      });
    this.recordingTimer = this.schedule(() => {
      this.recordingTimer = null;
      if (this.state.kind !== "recording") return;
      this.apply({ type: "recording_timed_out" });
      void this.finishRecording();
    }, VOICE_MAX_RECORDING_MS);
  }

  private beginReplyInterruptPress(): void {
    const pending = this.pendingReplyPress;
    this.pendingReplyPress = null;
    this.pressTimer = null;
    if (!pending || !this.options.isEnabled()) return;
    this.apply({ type: "reset" });
    this.apply({ type: "press_started", source: pending.source, atMs: pending.atMs });
    this.apply({ type: "press_elapsed", atMs: this.now() });
    if (this.currentState.kind === "recording") this.beginRecording();
  }

  private async finishRecording(): Promise<void> {
    const generation = this.operationGeneration;
    const start = this.recordingStart;
    this.recordingStart = null;
    try {
      await start;
      if (!this.isCurrentOperation(generation) || this.state.kind !== "transcribing") return;
      const turnId = this.activeTurnId;
      if (!turnId) return;
      const audio = await this.options.recorder.stop();
      if (!this.isCurrentOperation(generation) || this.state.kind !== "transcribing") return;
      const transcribe = await this.options.bridge.invoke({
        method: "voice.transcribe",
        payload: { audio_base64: Buffer.from(audio).toString("base64") },
      });
      if (!this.isCurrentOperation(generation) || this.state.kind !== "transcribing") return;
      if (transcribe.error) {
        this.apply({ type: "asr_failed", message: transcribe.error.message });
        return;
      }
      const text = String(transcribe.payload.text ?? "").trim();
      const asrMetrics = normalizeVoiceMetrics(transcribe.payload.metrics);
      this.apply({ type: "asr_succeeded", text });
      if (!this.isCurrentOperation(generation) || this.currentState.kind !== "sending") return;
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
          voice_turn_id: turnId,
          asr_metrics: asrMetrics ?? undefined,
        },
      });
      if (!this.isCurrentOperation(generation) || this.currentState.kind !== "sending") return;
      if (chat.error) {
        this.apply({ type: "chat_failed", message: chat.error.message });
        return;
      }
      this.apply({ type: "chat_accepted" });
    } catch (error: unknown) {
      if (!this.isCurrentOperation(generation)) return;
      if (this.state.kind === "transcribing") {
        this.apply({ type: "asr_failed", message: errorMessage(error, "语音识别失败，请重试") });
      } else if (this.state.kind === "sending") {
        this.apply({ type: "chat_failed", message: errorMessage(error, "消息发送失败") });
      }
    }
  }

  private isCurrentOperation(generation: number): boolean {
    return !this.disposed && generation === this.operationGeneration;
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

function normalizeVoiceMetrics(value: unknown): Record<string, string | number> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const metrics = value as Record<string, unknown>;
  const provider = String(metrics.provider ?? "").trim();
  if (!provider) return null;
  const nonNegativeNumber = (field: string) => {
    const raw = Number(metrics[field]);
    return Number.isFinite(raw) && raw >= 0 ? raw : 0;
  };
  return {
    provider,
    request_id: String(metrics.request_id ?? "").trim(),
    elapsed_ms: nonNegativeNumber("elapsed_ms"),
    audio_duration_ms: nonNegativeNumber("audio_duration_ms"),
    character_count: nonNegativeNumber("character_count"),
    error_code: String(metrics.error_code ?? "").trim(),
  };
}
