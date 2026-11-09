import type { BackgroundCtx, PluginBackgroundSettled, SurfaceCreateResult } from "@yinfengwindy/shiori-sdk";
import { isRecord, readPresentationIdentity, readPresentationState, type PetGesture, type PetPresentationIdentity, type PetPresentationState, type PetProviderReport } from "./protocol";

type Instance<Load extends PetProviderLoad> = { surfaceId: string; load: Load; placement: PluginBackgroundSettled | null; ready: boolean; shown: boolean; created: Promise<SurfaceCreateResult> };
/** Retained common state; each provider extends it with its own model data. */
export type PetProviderLoad = PetPresentationIdentity & { body: { width: number; height: number }; state: PetPresentationState };
/** Model decoding and animation mapping are the only format-specific operations. */
export type PetProviderOptions<Load extends PetProviderLoad> = {
  pluginId: string;
  prepare: (identity: PetPresentationIdentity, command: Record<string, unknown>, assetUrl: (path: string) => string | null) => Load;
  action?: (load: Load, command: Record<string, unknown>, moveDirection?: "left" | "right") => unknown;
  report: (value: PetProviderReport) => Promise<unknown>;
};
const fallbackPosition = { x: Number.MAX_SAFE_INTEGER, y: Number.MAX_SAFE_INTEGER };
/** Owns provider windows and presentation leases; every effect is scoped to a presentation lease. */
export class PetProviderController<Load extends PetProviderLoad> {
  private readonly instances = new Map<string, Instance<Load>>();
  private readonly revoked = new Set<string>();
  private disposed = false;
  constructor(private readonly ctx: Pick<BackgroundCtx, "surfaces" | "assets" | "reportFailure">, private readonly options: PetProviderOptions<Load>) {}

  /** Handles short backend commands; renderer readiness arrives separately. */
  async receive(value: unknown): Promise<void> {
    const identity = readPresentationIdentity(value);
    if (!identity || !isRecord(value)) throw new Error("形象呈现命令身份无效");
    try {
      if (value.op === "close") { await this.close(identity.lease_id); await this.send(identity, "closed"); return; }
      if (this.disposed || this.revoked.has(identity.lease_id)) return;
      if (value.op === "prepare") { await this.prepare(identity, value); return; }
      const instance = this.instances.get(identity.lease_id);
      if (!instance || instance.load.role_id !== identity.role_id || instance.load.model_id !== identity.model_id) throw new Error("形象呈现实例不存在");
      await instance.created;
      if (!this.owns(instance)) return;
      const state = value.state === undefined ? instance.load.state : readPresentationState(value.state);
      if (!state) throw new Error("形象展示状态无效");
      instance.load = { ...instance.load, state };
      if (value.op === "update") { this.ctx.surfaces.setState(instance.surfaceId, instance.load); return; }
      if (value.op === "hide") {
        instance.shown = false;
        this.ctx.surfaces.setInteraction(instance.surfaceId, null);
        this.ctx.surfaces.hide(instance.surfaceId);
        await this.send(identity, "hidden"); return;
      }
      if (value.op === "show") {
        if (!instance.ready) throw new Error("形象模型尚未加载");
        if (isRecord(value.position) && typeof value.position.x === "number" && typeof value.position.y === "number" && Number.isFinite(value.position.x) && Number.isFinite(value.position.y)) this.ctx.surfaces.setPosition(instance.surfaceId, { x: value.position.x, y: value.position.y });
        this.ctx.surfaces.setState(instance.surfaceId, instance.load);
        this.ctx.surfaces.setInteraction(instance.surfaceId, { roleId: identity.role_id, available: true });
        this.ctx.surfaces.show(instance.surfaceId); instance.shown = true;
        await this.send(identity, "shown"); return;
      }
      if (value.op === "action") { await this.action(instance, value.command); return; }
      throw new Error("形象呈现命令无效");
    } catch (error) {
      if (value.op === "prepare") await this.close(identity.lease_id);
      await this.send(identity, "failed", { error: error instanceof Error ? error.message : String(error) });
    }
  }
  /** Real window destruction/crash retires the lease before sending any callbacks. */
  async unavailable(value: unknown) {
    if (!isRecord(value) || value.plugin_id !== this.options.pluginId || typeof value.surface_id !== "string") return;
    const instance = [...this.instances.values()].find((item) => item.surfaceId === value.surface_id);
    if (!instance) return;
    await this.close(instance.load.lease_id);
    await this.send(instance.load, "lost", { error: "形象窗口已关闭或不可用" });
  }
  /** Revocation precedes awaiting creation, so late windows cannot reappear. */
  async dispose() {
    this.disposed = true;
    const instances = [...this.instances.values()];
    await Promise.all(instances.map(async (instance) => {
      await this.close(instance.load.lease_id);
      await this.send(instance.load, "lost", { error: "形象插件已停用" });
    }));
  }
  private async prepare(identity: PetPresentationIdentity, value: Record<string, unknown>) {
    if (this.instances.has(identity.lease_id)) throw new Error("形象实例已经存在");
    const load = this.options.prepare(identity, value, (path) => this.ctx.assets.url(path));
    const surfaceId = `pet-${identity.lease_id}`;
    const instance: Instance<Load> = { surfaceId, load, placement: null, ready: false, shown: false, created: Promise.resolve({ x: 0, y: 0, displayId: "" }) };
    this.instances.set(identity.lease_id, instance);
    this.ctx.surfaces.onMessage(surfaceId, (message) => { void this.message(instance, message).catch((error: unknown) => this.ctx.reportFailure("presentation.message", error)); });
    this.ctx.surfaces.onSettled(surfaceId, (placement) => {
      if (!this.owns(instance)) return;
      instance.placement = placement;
      if (instance.shown) void this.send(instance.load, "settled", { placement }).catch((error: unknown) => this.ctx.reportFailure("presentation.settled", error));
    });
    instance.created = this.ctx.surfaces.create(surfaceId, { body: load.body, visible: false }, fallbackPosition);
    const created = await instance.created;
    if (!this.owns(instance)) { await this.ctx.surfaces.destroy(surfaceId); return; }
    const area = await this.ctx.surfaces.workArea(surfaceId);
    if (!this.owns(instance)) return;
    instance.placement ??= { displayId: created.displayId, reason: "create", placement: { anchor: { x: created.x, y: created.y }, bodyOffset: { x: 0, y: 0 }, workArea: area } };
    this.ctx.surfaces.setState(surfaceId, load);
  }
  private async message(instance: Instance<Load>, value: unknown) {
    if (!this.owns(instance) || !isRecord(value)) return;
    if (value.kind === "model.ready" || value.kind === "model.failed") {
      if (value.lease_id !== instance.load.lease_id) return;
      if (value.kind === "model.failed") { await this.close(instance.load.lease_id); await this.send(instance.load, "failed", { error: typeof value.error === "string" ? value.error : "形象图加载失败" }); return; }
      if (!instance.ready) { instance.ready = true; await this.send(instance.load, "ready", instance.placement ? { placement: instance.placement } : {}); }
      return;
    }
    if (!instance.shown) return;
    let gesture: PetGesture;
    if (value.kind === "voice.gesture") {
      const phase = (["press", "move", "release", "cancel"] as const).find((item) => item === value.gesture);
      if (!phase) return;
      gesture = { kind: "voice.gesture", gesture: phase };
    } else if (value.kind === "hide" || value.kind === "voice.stop" || value.kind === "bubble.dismiss") gesture = { kind: value.kind };
    else return;
    await this.send(instance.load, "gesture", { gesture });
  }
  private async action(instance: Instance<Load>, value: unknown) {
    if (!instance.shown || !isRecord(value)) return;
    if (value.kind === "play") {
      const message = this.options.action?.(instance.load, value);
      if (message === undefined) throw new Error("模型不支持该动作");
      this.ctx.surfaces.post(instance.surfaceId, message); return;
    }
    const target = (["top_left", "top_right", "center", "bottom_left", "bottom_right"] as const).find((item) => item === value.target);
    if (value.kind !== "move" || !target) throw new Error("形象移动目标无效");
    const area = await this.ctx.surfaces.workArea(instance.surfaceId);
    if (!this.owns(instance) || !instance.shown) return;
    const { body } = instance.load;
    const position = target === "center" ? { x: area.x + (area.width - body.width) / 2, y: area.y + (area.height - body.height) / 2 }
      : { x: target.endsWith("left") ? area.x : area.x + area.width, y: target.startsWith("top") ? area.y : area.y + area.height };
    this.ctx.surfaces.moveTo(instance.surfaceId, position, 900);
    const message = this.options.action?.(instance.load, value, position.x < (instance.placement?.placement.anchor.x ?? position.x) ? "left" : "right");
    if (message !== undefined) this.ctx.surfaces.post(instance.surfaceId, message);
  }
  private owns(instance: Instance<Load>) { return !this.disposed && this.instances.get(instance.load.lease_id) === instance && !this.revoked.has(instance.load.lease_id); }
  private async close(leaseId: string) {
    this.revoked.add(leaseId);
    const instance = this.instances.get(leaseId);
    this.instances.delete(leaseId);
    if (!instance) return;
    await instance.created.catch(() => {});
    await this.ctx.surfaces.destroy(instance.surfaceId);
  }
  private async send(identity: PetPresentationIdentity, kind: PetProviderReport["kind"], extra: Partial<PetProviderReport> = {}) {
    await this.options.report({ ...extra, request_id: identity.request_id, lease_id: identity.lease_id, role_id: identity.role_id, model_id: identity.model_id, kind });
  }
}
