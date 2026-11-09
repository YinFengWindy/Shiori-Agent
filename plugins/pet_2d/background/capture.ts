import type { BackgroundCtx } from "@yinfengwindy/shiori-sdk";
import { isRecord, type PetProviderLoad } from "@yinfengwindy/shiori-pet";
import type { CaptureCommand, CapturePreferences, CaptureStatus } from "../capture/contracts";

type ActiveSurface = { surfaceId: string; leaseId: string; sessionId: string | null };
type PendingStop = { leaseId: string; sessionId: string; finish: () => void; timer: ReturnType<typeof setTimeout> };
/** Settings intent and shown-lease routing; camera/video resources stay inside the surface. */
export class CaptureCoordinator {
  private preferences: CapturePreferences;
  private enabled = false;
  private active: ActiveSurface | null = null;
  private phase: CaptureStatus["phase"] = "off";
  private error = "";
  private devices: CaptureStatus["devices"] = [];
  private disposed = false;
  private visibilityEpoch = 0;
  private readonly pendingStops = new Map<string, PendingStop>();
  private saveQueue = Promise.resolve();
  private readonly stored: Record<string, unknown>;
  constructor(private readonly ctx: Pick<BackgroundCtx, "surfaces" | "store" | "rpc" | "reportFailure">, stored: unknown) {
    this.stored = isRecord(stored) ? stored : {};
    const capture = isRecord(this.stored.capture) ? this.stored.capture : {};
    this.preferences = { deviceId: typeof capture.deviceId === "string" ? capture.deviceId : "", mirror: capture.mirror !== false };
  }
  /** Registers provider-private settings commands, with no backend RPC or media transport. */
  async register() {
    await this.ctx.rpc.handle("capture.status", () => this.snapshot());
    await this.ctx.rpc.handle("capture.configure", (value) => this.configure(value));
    await this.ctx.rpc.handle("capture.start", () => { this.start(); return this.snapshot(); });
    await this.ctx.rpc.handle("capture.stop", async () => { this.enabled = false; if (this.active) await this.stopSession(this.active); this.phase = "off"; return this.snapshot(); });
    await this.ctx.rpc.handle("capture.devices", () => { if (this.active) this.send(this.active, { kind: "capture.devices", leaseId: this.active.leaseId }); return this.snapshot(); });
    await this.ctx.rpc.handle("capture.calibrate", () => {
      if (!this.active?.sessionId || this.phase !== "tracking") throw new Error("尚未检测到可校准的人脸");
      this.send(this.active, { kind: "capture.calibrate", leaseId: this.active.leaseId, sessionId: this.active.sessionId }); return this.snapshot();
    });
  }
  /** Candidate windows have no capture authority until their actual show operation. */
  async visibility(load: PetProviderLoad, shown: boolean, surfaceId: string) {
    const epoch = ++this.visibilityEpoch;
    if (!shown) {
      if (this.active?.leaseId !== load.lease_id) return;
      const previous = this.active; this.active = null;
      this.phase = this.enabled ? "paused" : "off";
      await this.stopSession(previous); return;
    }
    if (this.disposed) return;
    if (this.active?.leaseId === load.lease_id) return;
    if (this.active) await this.stopSession(this.active);
    if (this.disposed || epoch !== this.visibilityEpoch) return;
    this.active = { surfaceId, leaseId: load.lease_id, sessionId: null };
    this.send(this.active, { kind: "capture.devices", leaseId: load.lease_id });
    if (this.enabled) this.startSession(this.active); else this.phase = "off";
  }
  /** Stop acknowledgements remain valid during lease teardown; every other report requires the shown lease. */
  message(load: PetProviderLoad, value: unknown): boolean {
    if (!isRecord(value) || typeof value.kind !== "string" || !value.kind.startsWith("capture.")) return false;
    if (value.leaseId !== load.lease_id) return true;
    if (value.kind === "capture.stopped" && typeof value.requestId === "string") {
      const pending = this.pendingStops.get(value.requestId);
      if (pending?.leaseId === load.lease_id && pending.sessionId === value.sessionId) pending.finish();
      return true;
    }
    const active = this.active;
    if (!active || active.leaseId !== load.lease_id) return true;
    if (value.kind === "capture.devices" && Array.isArray(value.devices)) {
      this.devices = value.devices.flatMap((item) => isRecord(item) && typeof item.deviceId === "string" && typeof item.label === "string" ? [{ deviceId: item.deviceId, label: item.label }] : []); return true;
    }
    if (value.kind === "capture.devices.error" && typeof value.error === "string") { this.error = value.error; return true; }
    if (value.sessionId !== active.sessionId || !active.sessionId) return true;
    if (value.kind === "capture.calibrated") { this.error = value.ok === true ? "" : "尚未检测到可校准的人脸"; return true; }
    if (value.kind === "capture.status") {
      const phase = (["starting", "tracking", "no_face", "error"] as const).find((candidate) => candidate === value.phase);
      if (phase) this.phase = phase;
      if (phase === "error") { this.enabled = false; active.sessionId = null; this.error = typeof value.error === "string" ? value.error : "面捕已停止"; }
    }
    return true;
  }
  /** Native window teardown is the final resource boundary when the context itself is retiring. */
  dispose() {
    this.disposed = true; this.enabled = false;
    const active = this.active; this.active = null;
    try { if (active?.sessionId) this.send(active, { kind: "capture.stop", leaseId: active.leaseId, sessionId: active.sessionId, requestId: crypto.randomUUID() }); }
    finally { for (const pending of [...this.pendingStops.values()]) pending.finish(); }
  }
  private snapshot(): CaptureStatus { return { enabled: this.enabled, available: this.active !== null, preferences: { ...this.preferences }, phase: this.phase, error: this.error, devices: this.devices.map((device) => ({ ...device })) }; }
  private start() {
    if (this.disposed || !this.active) throw new Error("请先显示 2.5D 形象");
    this.enabled = true; this.error = "";
    if (!this.active.sessionId) this.startSession(this.active);
  }
  private startSession(active: ActiveSurface) {
    if (this.disposed || !this.enabled || this.active !== active) return;
    active.sessionId = crypto.randomUUID(); this.phase = "starting"; this.error = "";
    this.send(active, { kind: "capture.start", leaseId: active.leaseId, sessionId: active.sessionId, preferences: this.preferences });
  }
  private configure(value: Record<string, unknown>) {
    const next: CapturePreferences = { deviceId: typeof value.deviceId === "string" ? value.deviceId : this.preferences.deviceId, mirror: typeof value.mirror === "boolean" ? value.mirror : this.preferences.mirror };
    const operation = this.saveQueue.then(async () => {
      if (this.disposed) throw new Error("面捕插件已停用");
      if (this.active?.sessionId) await this.stopSession(this.active);
      await this.ctx.store.write({ ...this.stored, capture: next }); this.preferences = next;
      if (this.active && this.enabled) this.startSession(this.active);
      return this.snapshot();
    });
    this.saveQueue = operation.then(() => {}, () => {}); return operation;
  }
  private async stopSession(active: ActiveSurface) {
    const sessionId = active.sessionId; active.sessionId = null;
    if (!sessionId) return;
    if (this.active === active) this.phase = this.enabled ? "paused" : "off";
    const requestId = crypto.randomUUID();
    await new Promise<void>((resolve) => {
      const finish = () => { const pending = this.pendingStops.get(requestId); if (!pending) return; clearTimeout(pending.timer); this.pendingStops.delete(requestId); resolve(); };
      const timer = setTimeout(() => {
        // A vanished/unresponsive renderer cannot acknowledge; closing its native
        // window releases the stream instead of leaving a hidden camera running.
        void this.ctx.surfaces.destroy(active.surfaceId).catch((error: unknown) => this.ctx.reportFailure("capture.stop", error)).finally(finish);
      }, 1_000);
      this.pendingStops.set(requestId, { leaseId: active.leaseId, sessionId, finish, timer });
      try { this.send(active, { kind: "capture.stop", leaseId: active.leaseId, sessionId, requestId }); }
      catch (error) { this.ctx.reportFailure("capture.stop", error); void this.ctx.surfaces.destroy(active.surfaceId).catch((cause: unknown) => this.ctx.reportFailure("capture.stop", cause)).finally(finish); }
    });
  }
  private send(active: ActiveSurface, command: CaptureCommand) { this.ctx.surfaces.post(active.surfaceId, command); }
}
