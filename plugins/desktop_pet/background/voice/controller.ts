import type { AsrResult, BackgroundCtx, BridgeEvent, NativeAudio } from "@yinfengwindy/shiori-sdk";
import type { VoicePreferences } from "./preferences";
import type { VoiceStatePayload } from "./types";
import { PetVoiceInput } from "./input";
import { PetReplyAudio } from "./replyAudio";
import type { PetSpeechQueue } from "./speechQueue";

type Turn = { role_id: string; session_key: string; mood: string; turn_id: string };
type PetVoiceContext = Pick<BackgroundCtx, "rpc" | "native" | "chat" | "reportFailure">;
/** Owns the desktop pet's ASR → chat → TTS interaction and exact turn matching. */
export class PetVoiceController {
  private roleId = "";
  private turn: Turn | null = null;
  private preferences: VoicePreferences;
  private disposed = false;
  private locked = false;
  private revision = 0;
  private keyRevision = 0;
  private keyTail = Promise.resolve();
  private readonly replies: PetReplyAudio;
  private readonly input: PetVoiceInput;
  constructor(private readonly ctx: PetVoiceContext, preferences: VoicePreferences, private readonly publish: (state: VoiceStatePayload) => void, speech: PetSpeechQueue) {
    this.preferences = preferences;
    const status = (status: VoiceStatePayload["status"], message?: string) => { if (!this.disposed) publish({ status, message }); };
    this.replies = new PetReplyAudio(ctx, speech, status);
    this.input = new PetVoiceInput(ctx.native.audio, {
      enabled: () => !this.disposed && !this.locked && this.preferences.enabled && Boolean(this.roleId),
      device: () => this.preferences.microphone_device_id, status,
      interrupt: () => this.retireReply(),
      captured: (audio, epoch) => this.captured(audio, epoch),
    });
  }
  /** Non-voice presentation supplies the current visible role without host selection policy. */
  bind(roleId: string) {
    if (roleId === this.roleId) return;
    this.stop(); this.roleId = roleId;
    void this.syncKeys();
  }
  /** The chosen synthesis service while pet speech is on; null means speech is off. */
  get ttsProvider() { return this.preferences.enabled ? this.preferences.tts : null; }
  async configure(preferences: VoicePreferences) { this.stop(); this.preferences = preferences; await this.syncKeys(); }
  /** Locking retires pending speech; unlocking admits new input without replay. */
  setLocked(locked: boolean) { this.locked = locked; if (locked) this.stop(); void this.syncKeys(); }
  gesture(gesture: string, source = "surface") {
    if (gesture === "press") this.input.press(source);
    else if (gesture === "move") this.input.move(source);
    else if (gesture === "release") void this.input.release(source);
    else if (gesture === "cancel") this.stop();
  }
  handle(event: BridgeEvent) {
    const turn = this.turn; const payload = event.payload;
    if (!turn || payload.turn_id !== turn.turn_id || payload.session_key !== turn.session_key || (payload.role_id !== undefined && payload.role_id !== turn.role_id)) return;
    const provider = this.preferences.tts;
    if (event.method === "chat.error") { this.stop(); this.publish({ status: "error", message: String(payload.message ?? "角色回复失败") }); return; }
    if (!provider) { if (event.method === "chat.done") { this.turn = null; this.publish({ status: "idle" }); } return; }
    if (event.method === "chat.delta") this.replies.push(String(payload.content_delta ?? payload.delta ?? ""), false, provider, turn.role_id, turn.mood);
    if (event.method === "chat.done") { this.replies.push(String(payload.reply ?? ""), true, provider, turn.role_id, turn.mood); this.turn = null; }
  }
  /** Retires current input and output before their outstanding promises can publish again. */
  stop() {
    this.revision += 1; this.input.cancel();
    this.retireReply();
  }
  private retireReply() {
    const turn = this.turn; this.turn = null;
    if (turn) void this.ctx.chat.cancel({ session_key: turn.session_key, turn_id: turn.turn_id }).catch((error) => this.ctx.reportFailure("voice.cancel", error));
    void this.replies.stop().catch((error) => this.ctx.reportFailure("voice.stop", error));
  }
  async dispose() { this.stop(); this.disposed = true; await this.syncKeys(); }
  private async captured(audio: NativeAudio, epoch: number) {
    const revision = this.revision; const roleId = this.roleId; const provider = this.preferences.asr;
    if (!provider) throw new Error("未选择语音识别服务商");
    const current = () => !this.disposed && this.input.current(epoch) && revision === this.revision && roleId === this.roleId;
    const result = await this.ctx.rpc.services.call<AsrResult>(provider, "transcribe", { audio_base64: audio.audio_base64, format: "wav" });
    if (!current()) return;
    if (!result.text.trim()) { this.publish({ status: "idle" }); return; }
    const context = await this.ctx.rpc.call<Omit<Turn, "turn_id">>("voice.context.get", { role_id: roleId });
    if (!current()) return;
    if (context.role_id !== roleId || !context.session_key) throw new Error("桌宠角色上下文已变化");
    const turn = { ...context, turn_id: crypto.randomUUID() };
    this.turn = turn; this.replies.begin(); this.publish({ status: "waiting_reply" });
    try { await this.ctx.chat.send({ role_id: roleId, turn_id: turn.turn_id, content: result.text.trim(), media: [] }); }
    catch (error) { if (this.turn === turn) this.retireReply(); throw error; }
  }
  private syncKeys() {
    const revision = ++this.keyRevision;
    this.keyTail = this.keyTail.then(async () => {
      if (revision !== this.keyRevision) return;
      try {
      await this.ctx.native.keys.unregister("speak"); await this.ctx.native.keys.unregister("stop");
      if (revision !== this.keyRevision || this.disposed || this.locked || !this.roleId || !this.preferences.enabled) return;
      await this.ctx.native.keys.register("speak", this.preferences.hotkey, (phase) => this.gesture(phase === "down" ? "press" : "release", "hotkey"));
      if (revision !== this.keyRevision) return;
      await this.ctx.native.keys.register("stop", "Escape", (phase) => { if (phase === "down") this.stop(); });
      } catch (error) { if (!this.disposed) this.ctx.reportFailure("voice.keys", error); }
    });
    return this.keyTail;
  }
}
