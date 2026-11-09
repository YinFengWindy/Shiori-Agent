import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { emptyPetReply, isRecord, petModelKey, readPetModelReference, type PetAction, type PetBinding, type PetGesture, type PetModelReference, type PetPresentationState, type PetProviderReport, type PetVoiceState } from "@yinfengwindy/shiori-pet";
import { ReplyBubbleController } from "./replyBubble";
import { desktopPetBindingPatch } from "./settings";
import { PetPresentationTransport } from "./presentation";
import type { DesktopPetSettings } from "./types";

type Instance = { binding: PetBinding; leaseId: string; shown: boolean; retired: boolean };
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
  private desiredVisible: boolean;
  private retryProvider: { epoch: number; pluginId: string } | null = null;
  private readonly listeners: Array<(roleId: string) => void> = [];
  constructor(private readonly options: DesktopPetControllerOptions) {
    this.settings = options.settings;
    this.desiredVisible = options.settings.visible;
    this.transport = new PetPresentationTransport(options.services, (report) => this.providerReport(report), options.timeoutMs);
    this.replies = new ReplyBubbleController((reply) => { this.state = { ...this.state, reply }; this.publish(); });
  }
  get isRunning() { return this.active?.shown ?? false; }
  get currentSettings() { return this.settings; }
  get visibleRoleId() { return this.target; }
  /** A model change within the same role does not restart speech or live output. */
  watchTarget(listener: (roleId: string) => void) { this.listeners.push(listener); }
  /** Receives completion before startup can block on it. */
  report(value: unknown) { this.transport.report(value); }
  /** Voice state is retained so surface reloads do not lose it. */
  publishVoice(voice: PetVoiceState) { this.state = { ...this.state, voice }; this.publish(); }
  /** Retains only the selected role's actual output level across model handover. */
  publishAudio(audio: PetPresentationState["audio"]) {
    this.state = { ...this.state, audio: this.target ? audio : null }; this.publish();
  }
  show() { return this.sync(true); }
  restore() { return this.sync(); }
  /** Late startup restores only the currently selected provider and visibility intent. */
  available(pluginId: string) {
    if (this.disposed || this.active || this.retryProvider?.epoch !== this.epoch || this.retryProvider.pluginId !== pluginId) return Promise.resolve();
    return this.sync();
  }
  /** Retires only provider instances named by the host's replacement publication.
   * Their RPC owners are already gone, so teardown must not call the successor.
   */
  providersReloaded(payload: unknown) {
    if (this.disposed || !isRecord(payload) || !Array.isArray(payload.plugin_ids)) return;
    const ids = new Set(payload.plugin_ids.filter((id): id is string => typeof id === "string"));
    const active = this.active, preparing = this.preparing;
    const activeRetired = active !== null && ids.has(active.binding.provider.plugin_id);
    const preparingRetired = preparing !== null && ids.has(preparing.binding.provider.plugin_id);
    const waitingProvider = this.retryProvider?.pluginId ?? this.settings.model?.provider.plugin_id;
    const waitingRetired = !active && !preparing && this.desiredVisible && waitingProvider !== undefined && ids.has(waitingProvider);
    if (!activeRetired && !preparingRetired && !waitingRetired) return;
    if (activeRetired) { active.retired = true; active.shown = false; this.transport.cancel(active.leaseId); }
    if (preparingRetired) { preparing.retired = true; preparing.shown = false; this.transport.cancel(preparing.leaseId); }
    // Do not invalidate an already queued hide: it still has to persist false.
    // A visible intent must invalidate accepted handovers and stale async commits.
    const epoch = this.desiredVisible ? this.newIntent(activeRetired) : this.epoch;
    if (activeRetired) { this.active = null; this.bind(""); }
    if (preparingRetired) this.preparing = null;
    if (this.desiredVisible && waitingProvider && ids.has(waitingProvider)) this.retryProvider = { epoch, pluginId: waitingProvider };
    this.options.onChanged?.();
  }
  hide() {
    this.desiredVisible = false;
    const epoch = this.newIntent(true);
    return this.enqueue(async () => { await this.closeActive(); if (this.current(epoch)) await this.save({ visible: false }); });
  }
  sync(forceVisible?: boolean) {
    if (forceVisible !== undefined) this.desiredVisible = forceVisible;
    const epoch = this.newIntent(forceVisible === false);
    return this.enqueue(async () => {
      if (!this.current(epoch)) return;
      if (forceVisible === false) await this.closeActive();
      let binding: PetBinding | null;
      try { binding = await this.options.resolveBinding(); }
      catch (error) { if (this.current(epoch)) await this.closeActive(); throw error; }
      if (!this.current(epoch)) return;
      if (!binding) { this.desiredVisible = false; await this.closeActive(); await this.save({ visible: false, roleId: null, model: null }); return; }
      const changed = this.settings.roleId !== binding.role_id || !this.settings.model || petModelKey(this.settings.model) !== bindingKey(binding);
      const visible = forceVisible ?? (changed || this.settings.visible);
      this.desiredVisible = visible;
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
    this.desiredVisible = false;
    this.newIntent(true); this.disposed = true; this.replies.dispose();
    await this.enqueue(() => this.closeActive());
    this.transport.dispose();
  }
  private async load(binding: PetBinding, epoch: number, commit?: () => Promise<unknown>) {
    const previous = this.active;
    if (previous && bindingKey(previous.binding) === bindingKey(binding) && previous.binding.role_id === binding.role_id) {
      // Identity survives a reversible handover hide. It does not prove that the
      // old window is still visible when a newer intent selects the same model.
      if (!previous.shown) await this.showInstance(previous);
      if (!this.current(epoch)) return;
      if (commit) await commit();
      return;
    }
    if (previous && previous.binding.role_id !== binding.role_id) await this.closeActive();
    const old = this.active;
    const next: Instance = { binding, leaseId: crypto.randomUUID(), shown: false, retired: false };
    this.preparing = next;
    try {
      const ready = await this.transport.request(binding, next.leaseId, "prepare", { state: this.state });
      if (!this.current(epoch)) return;
      const position = ready.placement ? this.settings.positions[`${binding.role_id}:${ready.placement.displayId}`] : undefined;
      if (old) {
        // The provider may hide before its completion reaches us. Retire the
        // visibility claim before waiting, including timeout/interruption paths.
        old.shown = false;
        await this.transport.request(old.binding, old.leaseId, "hide");
      }
      if (!this.current(epoch)) return;
      await this.showInstance(next, position);
      if (!this.current(epoch)) return;
      if (commit) await commit();
      if (!this.current(epoch)) return;
      this.active = next; this.preparing = null;
      this.bind(binding.role_id); this.publish();
      if (old) await this.close(old);
    } finally {
      if (this.preparing === next) this.preparing = null;
      if (this.active !== next) {
        // A new intent also aborts this handover without throwing. Always close
        // its candidate before restoring the old window, preserving one visible
        // instance. An explicit hide/disable revokes target and must stay hidden.
        await this.close(next);
        if (old && this.active === old && !old.shown && !this.disposed && this.target === old.binding.role_id) {
          try { await this.showInstance(old); }
          catch (restoreError) { this.failure(old, restoreError); }
        }
      }
    }
  }
  private async showInstance(instance: Instance, position?: { x: number; y: number }) {
    if (instance.retired) throw new Error("桌宠呈现实例已撤销");
    await this.transport.request(instance.binding, instance.leaseId, "show", { state: this.state, ...(position ? { position } : {}) });
    instance.shown = true;
  }
  private publish() {
    const active = this.active;
    if (active && !active.retired) void this.transport.update(active.binding, active.leaseId, "update", { state: this.state }).catch((error: unknown) => this.failure(active, error));
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
    if (revoke) {
      this.bind("");
      if (this.active) this.transport.cancel(this.active.leaseId);
    }
    return this.epoch;
  }
  private current(epoch: number) { return !this.disposed && this.epoch === epoch; }
  private bind(roleId: string) {
    if (this.target === roleId) return;
    this.state = { ...this.state, audio: null };
    this.target = roleId; this.replies.bind(roleId);
    for (const listener of this.listeners) listener(roleId);
  }
  private async closeActive() { const active = this.active; this.active = null; this.bind(""); if (active) await this.close(active); }
  private async close(instance: Instance) {
    instance.shown = false;
    this.transport.cancel(instance.leaseId);
    if (instance.retired) return;
    try { await this.transport.request(instance.binding, instance.leaseId, "close"); }
    catch (error) { this.options.onError("presentation.close", error); }
  }
  private enqueue<T>(operation: () => Promise<T>): Promise<T> { const next = this.queue.then(operation, operation); this.queue = next.then(() => {}, () => {}); return next; }
  private async save(patch: Partial<DesktopPetSettings>) { this.settings = { ...this.settings, ...patch }; await this.options.saveSettings(this.settings); this.options.onChanged?.(); }
}
function bindingKey(binding: PetBinding) { return petModelKey({ provider: binding.provider, model_id: binding.model.id }); }
