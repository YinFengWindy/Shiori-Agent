import { ReplyBubbleController } from "./replyBubble";
import { emptyPetReply, type PetReplyBubble } from "../shared/replyBubble";
import type {
  PluginBackgroundSettled,
  PluginBackgroundSurfaces,
} from "../../../apps/desktop/renderer/src/background/pluginBackgroundRegistry";
import { desktopPetBindingPatch } from "./settings";
import {
  desktopPetBody,
  type DesktopPetActionPayload,
  type DesktopPetBinding,
  type DesktopPetPosition,
  type DesktopPetSettings,
  type DesktopPetState,
  type DesktopPetWorkArea,
} from "./types";

/** Keeps role-requested moves visible as a short, deliberate desktop animation. */
export const desktopPetAgentMoveDurationMs = 900;

/** Names the pet's window within this plugin's own surfaces. */
export const desktopPetSurfaceId = "pet";

/**
 * A deliberately unreachable anchor, used when the pet has no remembered
 * position: the host clamps the body into the work area, which lands it in the
 * bottom-right corner of whichever display the surface opened on — the same
 * fallback the pet had before it moved onto surfaces.
 */
const desktopPetFallbackAnchor: DesktopPetPosition = {
  x: Number.MAX_SAFE_INTEGER,
  y: Number.MAX_SAFE_INTEGER,
};

/** Settle reasons that mean the user (or a role) actually relocated the pet. */
const persistedSettleReasons = new Set(["drag", "momentum", "move"]);

/** The slice of `ctx.surfaces` this controller uses; narrowed so tests can fake it. */
export type DesktopPetSurfaces = Pick<
  PluginBackgroundSurfaces,
  "create" | "destroy" | "setPosition" | "moveTo" | "post" | "setState" | "workArea"
>;

export type DesktopPetControllerOptions = {
  surfaces: DesktopPetSurfaces;
  /** The settings already read out of `ctx.store`; the controller owns them from here. */
  settings: DesktopPetSettings;
  saveSettings: (settings: DesktopPetSettings) => Promise<void>;
  resolveBinding: () => Promise<DesktopPetBinding | null>;
  /** Reports a failure from a fire-and-forget path that has no caller to throw at. */
  onError?: (operation: string, error: unknown) => void;
  /**
   * Called after anything that changes what the pet's tray item should say.
   *
   * The pet is the only thing that knows whether it is showing and whether it
   * has a binding to show, and since #181-D it owns the menu item that reports
   * both. Position writes call this too — they are cheap to ignore, and the
   * alternative is this class deciding what its consumer considers a change.
   */
  onChanged?: () => void;
};

/**
 * The desktop pet's always-resident orchestration, running in the plugin-host
 * renderer as this plugin's `app.background` contribution.
 *
 * Moved out of the Electron main process by #181-C. The host now knows nothing
 * about roles, packages, sprite states or remembered positions: it provides
 * DesktopSurface, a per-plugin store and a backend RPC namespace, and this
 * class is the only thing that puts those together into "a pet". The reason it
 * is not in the main process is recorded on #181: a plugin's timers and
 * listeners there could never be reclaimed on disable, so "停用插件后订阅全部
 * 回收" could only be pretended.
 *
 * What stays in the host, and why, is listed in
 * `apps/desktop/src/pluginCoupling/desktopPet.ts`.
 */
export class DesktopPetController {
  private readonly surfaces: DesktopPetSurfaces;
  private queue = Promise.resolve();
  private settings: DesktopPetSettings;
  private activeRoleId = "";
  private activeLoad: { binding: DesktopPetBinding; state: DesktopPetState } | null = null;
  private latestReply: PetReplyBubble = emptyPetReply;
  /** Reply lifecycle is owned and reclaimed alongside this plugin controller. */
  readonly replies: ReplyBubbleController;
  private running = false;
  /**
   * Set the moment teardown starts, and never cleared.
   *
   * `terminate()` going through the queue is what orders the destroy after any
   * operation already running; this flag is what stops that operation from
   * doing pointless work on the way. A `show()` parked on `resolveBinding()` —
   * a round trip to the Python backend — resumes *after* the plugin was
   * disabled, and without this it would open a window purely so the queued
   * destroy could close it again, which the user sees as a flash.
   *
   * Checked only where an await inside the queue can straddle teardown, i.e.
   * right after `resolveBinding` in `show` and `sync`. Adding more checks
   * further in would be unreachable: the queue already guarantees nothing else
   * runs between those points and the destroy.
   */
  private disposed = false;
  /**
   * Where the surface last came to rest, and on which display.
   *
   * Cached rather than asked for, because both answers arrive unprompted: the
   * creation result carries them, and every settle refreshes them. The old
   * main-process controller could call `anchorFromWindow` to re-read the
   * window's real bounds; from a renderer that would be an IPC round trip.
   *
   * The one place a stale value shows: `handleAgentAction` compares this
   * against the move target to pick `running-left` vs `running-right`. Two
   * role-requested moves in quick succession — or one issued mid-glide, before
   * the settle lands — can read the pre-move anchor and face the sprite the
   * wrong way for the duration of the move. Cosmetic, and not worth an IPC
   * round trip per action, but it is not "nothing".
   */
  private anchor: DesktopPetPosition = desktopPetFallbackAnchor;
  private displayId = "";

  constructor(private readonly options: DesktopPetControllerOptions) {
    this.surfaces = options.surfaces;
    this.settings = options.settings;
    this.replies = new ReplyBubbleController((payload) => {
      this.latestReply = payload;
      this.pushRetainedState();
    });
  }

  /**
   * Whether the pet's surface is currently up.
   *
   * Tracked locally rather than asked of the host, which is the one place this
   * controller can disagree with reality: if the OS or Electron destroyed the
   * window behind our back, the host has forgotten the surface while this flag
   * still says it exists. The pet's window is frameless and always-on-top with
   * no close affordance, so in practice that only happens during shutdown,
   * when nothing reads this again.
   */
  get isRunning(): boolean {
    return this.running;
  }

  /** The settings as last saved, for callers that need the current binding. */
  get currentSettings(): DesktopPetSettings {
    return this.settings;
  }

  /**
   * Records where the surface came to rest.
   *
   * Driven by `ctx.surfaces.onSettled` rather than from here, because a drag or
   * release glide is started by the surface renderer talking to the host
   * directly; this controller never sees those calls.
   */
  handleSettled(settled: PluginBackgroundSettled): void {
    this.anchor = settled.placement.anchor;
    this.displayId = settled.displayId;
    if (!persistedSettleReasons.has(settled.reason) || !this.activeRoleId) return;
    this.persistPosition(this.activeRoleId, settled.placement.anchor);
  }

  show(): Promise<void> {
    return this.enqueue(async () => {
      const binding = await this.options.resolveBinding();
      // Teardown can land inside the round trip above; from here on there is
      // nothing left to reclaim what this would build or write.
      if (this.disposed) return;
      if (!binding) throw new Error("没有已启用且已选择素材的桌宠角色");
      await this.load(binding, "idle");
      if (this.disposed) return;
      await this.saveSettings(desktopPetBindingPatch(binding, true));
    });
  }

  hide(): Promise<void> {
    return this.enqueue(async () => {
      await this.destroySurface();
      await this.saveSettings({ visible: false });
    });
  }

  sync(forceVisible?: boolean): Promise<void> {
    return this.enqueue(async () => {
      const binding = await this.options.resolveBinding();
      if (this.disposed) return;
      if (!binding) {
        await this.destroySurface();
        await this.saveSettings({ visible: false, roleId: null, packageId: null });
        return;
      }
      const current = this.settings;
      const changedBinding = current.roleId !== binding.roleId || current.packageId !== binding.package.id;
      const visible = forceVisible ?? (changedBinding || current.visible);
      if (visible) await this.load(binding, "idle");
      else await this.destroySurface();
      if (this.disposed) return;
      await this.saveSettings(desktopPetBindingPatch(binding, visible));
    });
  }

  restore(): Promise<void> {
    return this.sync();
  }

  play(state: DesktopPetState): void {
    this.postPlay(state, false);
  }

  /** Executes one already-authorized role action without exposing window APIs to the renderer. */
  handleAgentAction(value: unknown): void {
    if (!isDesktopPetActionPayload(value)) return;
    if (!this.running || value.role_id !== this.activeRoleId || value.channel !== "desktop") return;
    if (value.kind === "play") {
      const state = value.name ? this.activeLoad?.binding.actions?.[value.name] : undefined;
      if (state) this.postPlay(state, true);
      return;
    }
    const target = value.target;
    if (!target) return;
    const current = this.anchor;
    void this.surfaces.workArea(desktopPetSurfaceId).then((workArea) => {
      // The surface can be torn down while the work area is in flight; moving a
      // surface that no longer exists would be reported as a host error.
      if (!this.running) return;
      const next = desktopPetTargetPosition(target, workArea);
      // The host runs the tween and reports the landing through `handleSettled`.
      this.surfaces.moveTo(desktopPetSurfaceId, next, desktopPetAgentMoveDurationMs);
      if (value.animation === "run") {
        const state = next.x < current.x ? "running-left" : next.x > current.x ? "running-right" : "idle";
        this.postPlay(state, true);
      }
    }).catch((error) => this.options.onError?.("pet-action", error));
  }

  /** Tears the pet's window down when the plugin is disabled or reloaded. */
  async terminate(): Promise<void> {
    this.disposed = true;
    this.replies.dispose();
    // Through the queue, so a `show()` that is mid-flight finishes (and bails
    // on `disposed`) before the destroy runs, rather than racing it.
    await this.enqueue(() => this.destroySurface());
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.queue.then(operation, operation);
    this.queue = next.catch(() => undefined);
    return next;
  }

  private async load(binding: DesktopPetBinding, state: DesktopPetState): Promise<void> {
    // Host window creation is an IPC round trip. Retain replies arriving after
    // the role is resolved but before the new surface acknowledges creation.
    this.replies.bind(binding.roleId);
    if (!this.running) {
      // Created at the fallback corner first: only once the window exists can
      // the host say which display it landed on, and the remembered position is
      // per display. `create` answers with both, so the remembered position is
      // applied without a second round trip.
      //
      // Being applied before the surface paints is a practical consequence, not
      // a guarantee: `create` and `setPosition` are two messages from this
      // renderer, while the first paint happens in the *surface's* renderer
      // after it has loaded its HTML — which is far slower than one IPC hop,
      // but nothing enforces the ordering. Before #181-C this was a real
      // invariant, because both calls were synchronous inside the main process.
      const placement = await this.surfaces.create(
        desktopPetSurfaceId,
        { body: desktopPetBody },
        desktopPetFallbackAnchor,
      ).catch((error: unknown) => {
        this.replies.bind("");
        throw error;
      });
      if (this.disposed) return;
      this.running = true;
      this.anchor = { x: placement.x, y: placement.y };
      this.displayId = placement.displayId;
      // Read from `this.settings` rather than from a caller's snapshot: a
      // settle can have written a position while `create` was in flight.
      const remembered = this.settings.positions[positionKey(binding.roleId, placement.displayId)];
      if (remembered) this.surfaces.setPosition(desktopPetSurfaceId, remembered);
    }
    this.activeRoleId = binding.roleId;
    this.activeLoad = { binding, state };
    // Retained, so a renderer that mounts or reloads later still gets it.
    this.pushRetainedState();
  }

  private pushRetainedState(): void {
    if (!this.activeLoad || !this.running) return;
    this.surfaces.setState(desktopPetSurfaceId, {
      load: {
        package: this.activeLoad.binding.package,
        state: this.activeLoad.state,
      },
      reply: this.latestReply,
    });
  }

  /** One-shot sprite command; never retained, so a reload does not replay it. */
  private postPlay(state: DesktopPetState, transient: boolean): void {
    if (!this.running) return;
    this.surfaces.post(desktopPetSurfaceId, { state, transient });
  }

  /**
   * Merges a change into the current settings and persists the result.
   *
   * A patch rather than a whole snapshot, because `persistPosition` runs
   * *outside* the queue — a settle is pushed in from the host whenever the user
   * lets go of the pet — and can land between a queued operation taking its
   * snapshot and that operation saving it. Saving a whole snapshot would then
   * write back the positions as they were before the drag, silently losing it.
   */
  private async saveSettings(patch: Partial<DesktopPetSettings>): Promise<void> {
    // In memory first: a failed write must not leave this controller acting on
    // a binding it has already replaced.
    this.settings = { ...this.settings, ...patch };
    await this.options.saveSettings(this.settings);
    this.options.onChanged?.();
  }

  private persistPosition(roleId: string, position: DesktopPetPosition): void {
    void this.saveSettings({
      positions: { ...this.settings.positions, [positionKey(roleId, this.displayId)]: position },
    }).catch((error) => {
      this.options.onError?.("persist-position", error);
    });
  }

  private async destroySurface(): Promise<void> {
    // Called unconditionally rather than only when `running`: the host treats
    // an unknown surface as a no-op, and doing it this way also reclaims a
    // window this controller has somehow lost track of.
    await this.surfaces.destroy(desktopPetSurfaceId);
    this.running = false;
    this.activeRoleId = "";
    this.activeLoad = null;
    this.replies.bind("");
  }
}

/** Positions are remembered per role *and* display, so unplugging a monitor does not move the pet. */
function positionKey(roleId: string, displayId: string): string {
  return `${roleId}:${displayId}`;
}

function isDesktopPetActionPayload(value: unknown): value is DesktopPetActionPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Partial<DesktopPetActionPayload>;
  return payload.channel === "desktop"
    && typeof payload.role_id === "string"
    && (payload.kind === "move" || payload.kind === "play");
}

/**
 * Resolves a named corner or the centre of a work area.
 *
 * The corners deliberately overshoot: the host clamps the body into the work
 * area, so `{ workArea.x + workArea.width, ... }` lands exactly at the right
 * edge without this function having to repeat the body arithmetic. Only the
 * centre genuinely needs the body size.
 */
function desktopPetTargetPosition(
  target: NonNullable<DesktopPetActionPayload["target"]>,
  workArea: DesktopPetWorkArea,
): DesktopPetPosition {
  const right = workArea.x + workArea.width;
  const bottom = workArea.y + workArea.height;
  if (target === "top_left") return { x: workArea.x, y: workArea.y };
  if (target === "top_right") return { x: right, y: workArea.y };
  if (target === "bottom_left") return { x: workArea.x, y: bottom };
  if (target === "bottom_right") return { x: right, y: bottom };
  return {
    x: workArea.x + (workArea.width - desktopPetBody.width) / 2,
    y: workArea.y + (workArea.height - desktopPetBody.height) / 2,
  };
}
