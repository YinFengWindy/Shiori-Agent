import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { emptyPetReply, isRecord, petModelKey, readPetModelReference, type PetAction, type PetBinding, type PetGesture, type PetModelReference, type PetPresentationState, type PetProviderReport, type PetVoiceState } from "@yinfengwindy/shiori-pet";
import { ReplyBubbleController } from "./replyBubble";
import { desktopPetBindingPatch } from "./settings";
import { PetPresentationTransport } from "./presentation";
import type { DesktopPetSettings } from "./types";

type Instance = { binding: PetBinding; leaseId: string };
/** Desktop-owned policy, with format-specific effects behind services. */
export type DesktopPetControllerOptions = {
  services: PluginRpcClient["services"];
  settings: DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: () => Promise<PetBinding | null>;
  preview: (roleId: string, model: PetModelReference) => Promise<PetBinding>;
  select: (roleId: string, model: PetModelReference) => Promise<unknown>;
  onError: (operation: string, error: unknown) => void;
  onChanged?: () => void;
  onGesture?: (gesture: PetGesture) => void;
  timeoutMs?: number;
};

/** Owns selection, replies and visibility, independent of the rendering format. */
export class DesktopPetController {
  readonly replies: ReplyBubbleController;
  private readonly transport: PetPresentationTransport;
  private settings: DesktopPetSettings;
  private state: PetPresentationState = { reply: emptyPetReply, voice: { status: "idle" } };
  private active: Instance | null = null;
  private preparing: Instance | null = null;
  private queue = Promise.resolve();
  private epoch = 0;
  private disposed = false;
  private target = "";
  private retryProvider: { epoch: number; pluginId: string } | null = null;
  private readonly listeners: Array<(roleId: string) => void> = [];
  constructor(private readonly options: DesktopPetControllerOptions) {
    this.settings = options.settings;
    this.transport = new PetPresentationTransport(options.services, (report) => this.providerReport(report), options.timeoutMs);
    this.replies = new ReplyBubbleController((reply) => { this.state = { ...this.state, reply }; this.publish(); });
  }
  get isRunning() { return this.active !== null; }
  get currentSettings() { return this.settings; }
  get visibleRoleId() { return this.target; }
  /** A model change within the same role does not restart speech or live output. */
  watchTarget(listener: (roleId: string) => void) { this.listeners.push(listener); }
  /** Receives completion before startup can block on it. */
  report(value: unknown) { this.transport.report(value); }
  /** Voice state is retained so surface reloads do not lose it. */
  publishVoice(voice: PetVoiceState) { this.state = { ...this.state, voice }; this.publish(); }
  show() { return this.sync(true); }
  restore() { return this.sync(); }
  /** Late startup restores only the currently selected provider and visibility intent. */
  available(pluginId: string) {
    if (this.disposed || this.active || this.retryProvider?.epoch !== this.epoch || this.retryProvider.pluginId !== pluginId) return Promise.resolve();
    return this.sync();
  }
  hide() {
    const epoch = this.newIntent(true);
    return this.enqueue(async () => { await this.closeActive(); if (this.current(epoch)) await this.save({ visible: false }); });
  }
  sync(forceVisible?: boolean) {
    const epoch = this.newIntent(forceVisible === false);
    return this.enqueue(async () => {
      if (!this.current(epoch)) return;
      if (forceVisible === false) await this.closeActive();
      let binding: PetBinding | null;
      try { binding = await this.options.resolveBinding(); }
      catch (error) { if (this.current(epoch)) await this.closeActive(); throw error; }
      if (!this.current(epoch)) return;
      if (!binding) { await this.closeActive(); await this.save({ visible: false, roleId: null, model: null }); return; }
      const changed = this.settings.roleId !== binding.role_id || !this.settings.model || petModelKey(this.settings.model) !== bindingKey(binding);
      const visible = forceVisible ?? (changed || this.settings.visible);
      if (visible) {
        this.retryProvider = { epoch, pluginId: binding.provider.plugin_id };
        await this.load(binding, epoch);
        if (this.current(epoch)) this.retryProvider = null;
      } else await this.closeActive();
      if (this.current(epoch)) await this.save(desktopPetBindingPatch(binding, visible));
    });
  }
  /** Active-role replacements prepare before changing the authoritative selection. */
  select(value: unknown) {
    const reference = readPetModelReference(value);
    if (!reference || !isRecord(value) || typeof value.role_id !== "string" || !value.role_id) return Promise.reject(new Error("桌宠选择无效"));
    const roleId = value.role_id;
    // Editing another role's model must not retire an active role's pending load.
    if (this.active?.binding.role_id !== roleId && this.preparing?.binding.role_id !== roleId && this.settings.roleId !== roleId) return this.options.select(roleId, reference);
    const epoch = this.newIntent(false);
    return this.enqueue(async () => {
      if (!this.current(epoch)) return;
      if (!this.active || this.active.binding.role_id !== roleId) {
        const result = await this.options.select(roleId, reference);
        if (this.current(epoch) && this.settings.roleId === roleId) await this.save({ model: reference });
        return result;
      }
      const binding = await this.options.preview(roleId, reference);
      if (!this.current(epoch)) return;
      await this.load(binding, epoch, () => this.options.select(roleId, reference));
      if (this.current(epoch)) await this.save(desktopPetBindingPatch(binding, true));
    });
  }
  /** Only model-supported names are sent; movement does not mention sprite rows. */
  handleAgentAction(value: unknown) {
    const active = this.active;
    if (!active || !isRecord(value) || value.channel !== "desktop" || value.role_id !== active.binding.role_id) return;
    let command: PetAction;
    if (value.kind === "play" && typeof value.name === "string" && active.binding.model.actions.includes(value.name)) command = { kind: "play", name: value.name };
    else {
      const target = (["top_left", "top_right", "center", "bottom_left", "bottom_right"] as const).find((item) => item === value.target);
      if (value.kind !== "move" || !target) return;
      command = { kind: "move", target, animation: value.animation === "run" ? "run" : "" };
    }
    void this.transport.update(active.binding, active.leaseId, "action", { command }).catch((error: unknown) => this.failure(active, error));
  }
  /** Ends presentation and waiting callbacks when the background stops. */
  async terminate() {
    if (this.disposed) return;
    this.newIntent(true); this.disposed = true; this.replies.dispose();
    await this.enqueue(() => this.closeActive());
    this.transport.dispose();
  }
  private async load(binding: PetBinding, epoch: number, commit?: () => Promise<unknown>) {
    const previous = this.active;
    if (previous && bindingKey(previous.binding) === bindingKey(binding) && previous.binding.role_id === binding.role_id) { if (commit) await commit(); return; }
    if (previous && previous.binding.role_id !== binding.role_id) await this.closeActive();
    const old = this.active;
    const next: Instance = { binding, leaseId: crypto.randomUUID() };
    this.preparing = next;
    let oldHidden = false;
    try {
      const ready = await this.transport.request(binding, next.leaseId, "prepare", { state: this.state });
      if (!this.current(epoch)) return;
      const position = ready.placement ? this.settings.positions[`${binding.role_id}:${ready.placement.displayId}`] : undefined;
      if (old) { await this.transport.request(old.binding, old.leaseId, "hide"); oldHidden = true; }
      if (!this.current(epoch)) return;
      await this.transport.request(binding, next.leaseId, "show", { state: this.state, ...(position ? { position } : {}) });
      if (!this.current(epoch)) return;
      if (commit) await commit();
      if (!this.current(epoch)) return;
      this.active = next; this.preparing = null;
      this.bind(binding.role_id); this.publish();
      if (old) await this.close(old);
    } catch (error) {
      if (oldHidden && old && this.current(epoch)) {
        await this.close(next);
        try { await this.transport.request(old.binding, old.leaseId, "show", { state: this.state }); }
        catch (restoreError) { this.failure(old, restoreError); }
      }
      throw error;
    } finally {
      if (this.preparing === next) this.preparing = null;
      if (this.active !== next) await this.close(next);
    }
  }
  private publish() {
    const active = this.active;
    if (active) void this.transport.update(active.binding, active.leaseId, "update", { state: this.state }).catch((error: unknown) => this.failure(active, error));
  }
  private providerReport(report: PetProviderReport) {
    const active = this.active;
    if (!active || active.leaseId !== report.lease_id || active.binding.role_id !== report.role_id || active.binding.model.id !== report.model_id) return;
    if (report.kind === "lost" || report.kind === "failed") { this.failure(active, new Error(report.error || "桌宠形象不可用")); return; }
    if (report.kind === "settled" && report.placement && ["drag", "momentum", "move"].includes(report.placement.reason)) {
      const { displayId, placement: { anchor } } = report.placement;
      if (typeof displayId !== "string" || !Number.isFinite(anchor.x) || !Number.isFinite(anchor.y)) return;
      void this.save({ positions: { ...this.settings.positions, [`${report.role_id}:${displayId}`]: anchor } }).catch((error: unknown) => this.options.onError("position", error));
    }
    if (report.kind === "gesture" && report.gesture) {
      if (report.gesture.kind === "hide") void this.hide().catch((error: unknown) => this.options.onError("hide", error));
      else if (report.gesture.kind === "bubble.dismiss") this.replies.dismiss();
      else this.options.onGesture?.(report.gesture);
    }
  }
  private failure(instance: Instance, error: unknown) {
    if (this.active !== instance) return;
    this.active = null; this.bind(""); this.options.onError("presentation", error);
    void this.close(instance); this.options.onChanged?.();
  }
  private newIntent(revoke: boolean) {
    this.epoch += 1;
    this.retryProvider = null;
    if (this.preparing) this.transport.cancel(this.preparing.leaseId);
    if (revoke) this.bind("");
    return this.epoch;
  }
  private current(epoch: number) { return !this.disposed && this.epoch === epoch; }
  private bind(roleId: string) {
    if (this.target === roleId) return;
    this.target = roleId; this.replies.bind(roleId);
    for (const listener of this.listeners) listener(roleId);
  }
  private async closeActive() { const active = this.active; this.active = null; this.bind(""); if (active) await this.close(active); }
  private async close(instance: Instance) {
    this.transport.cancel(instance.leaseId);
    try { await this.transport.request(instance.binding, instance.leaseId, "close"); }
    catch (error) { this.options.onError("presentation.close", error); }
  }
  private enqueue<T>(operation: () => Promise<T>): Promise<T> { const next = this.queue.then(operation, operation); this.queue = next.then(() => {}, () => {}); return next; }
  private async save(patch: Partial<DesktopPetSettings>) { this.settings = { ...this.settings, ...patch }; await this.options.saveSettings(this.settings); this.options.onChanged?.(); }
}
function bindingKey(binding: PetBinding) { return petModelKey({ provider: binding.provider, model_id: binding.model.id }); }
