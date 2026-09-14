import {
  noSurfaceExtension,
  type SurfaceBounds,
  type SurfaceExtension,
  type SurfacePoint,
  type SurfaceSpec,
  type SurfaceWorkArea,
} from "./contract.js";
import {
  clampSurfaceAnchor,
  surfaceAnchorFromCursor,
  surfaceAnchorFromWindowBounds,
  surfaceBodyOffset,
  surfaceWindowBounds,
} from "./geometry.js";
import {
  advanceSurfaceMomentum,
  shouldStopSurfaceMomentum,
  surfaceMomentumIntervalMs,
  type SurfaceMomentum,
  type SurfaceMomentumConfig,
} from "./momentum.js";

/** Cursor-follow cadence during a drag, matched to a 60Hz display. */
export const surfaceDragFollowIntervalMs = 1000 / 60;
/** Frame cadence for host-driven eased moves. */
export const surfaceMoveFrameMs = 16;

/**
 * The slice of an Electron `BrowserWindow` a surface needs.
 *
 * Declared structurally so `DesktopSurfaceHost` stays importable — and
 * therefore testable — outside an Electron process. `window.ts` supplies the
 * production implementation.
 */
export type SurfaceWindowHandle = {
  /** Stable per-window identity, used to attribute an IPC message to a surface. */
  readonly id: number;
  setBounds(bounds: SurfaceBounds): void;
  getBounds(): SurfaceBounds;
  isDestroyed(): boolean;
  destroy(): void;
  showInactive(): void;
  hide(): void;
  setIgnoreMouseEvents(ignore: boolean, options?: { forward?: boolean }): void;
  send(channel: string, payload: unknown): void;
  onClosed(listener: () => void): void;
};

type TimerHandle = { readonly __surfaceTimer?: never } | ReturnType<typeof setTimeout>;

/**
 * Why a surface came to rest, for the in-process settle observer.
 *
 * A plugin's host-side code often wants to remember where its surface ended
 * up, but only some of these reasons represent the user moving it: growing a
 * panel or replaying state on reload lands the surface at the position it
 * already had, and treating those as a move means rewriting persisted state
 * every time a bubble appears.
 */
export type SurfaceSettleReason =
  | "create"
  | "position"
  | "extension"
  | "drag"
  | "momentum"
  | "move"
  | "ready";

/** Where a surface settled, as reported to both the renderer and the settle observer. */
export type SurfacePlacementInfo = {
  anchor: SurfacePoint;
  bodyOffset: SurfacePoint;
  workArea: SurfaceWorkArea;
};

export type DesktopSurfaceHostOptions = {
  createWindow(key: SurfaceKey, spec: SurfaceSpec): SurfaceWindowHandle;
  workAreaFor(window: SurfaceWindowHandle): SurfaceWorkArea;
  /**
   * Stable identity of the display a surface sits on.
   *
   * Separate from `workAreaFor` because a work area is a rectangle: two
   * displays can present the same one, and a single display's changes when a
   * taskbar moves. Callers that remember a per-display position need identity,
   * not geometry.
   */
  displayIdFor?(window: SurfaceWindowHandle): string;
  cursorScreenPoint(): SurfacePoint;
  /**
   * Notified in-process whenever a surface comes to rest.
   *
   * Deliberately not an IPC message at this level: `main.ts` is the one
   * observer, and it forwards each settle to the plugin-host renderer on
   * `surfaceSettledChannel` so the owning plugin's `app.background` code can
   * decide whether the new position is worth remembering (#181-C). Never
   * called from a drag, glide or tween frame.
   */
  onSettled?(key: SurfaceKey, placement: SurfacePlacementInfo, reason: SurfaceSettleReason): void;
  /** Opens a native context menu over a surface; resolves the chosen id, or null. */
  showContextMenu?(
    window: SurfaceWindowHandle,
    items: SurfaceMenuItem[],
  ): Promise<string | null>;
  /** Brings the main application window forward; a surface has no other way to. */
  activateMainWindow?(): void;
  /** Injectable so glide and tween arithmetic is deterministic under test. */
  now?: () => number;
  setTimer?: (callback: () => void, delayMs: number) => TimerHandle;
  clearTimer?: (handle: TimerHandle) => void;
};

/** One entry of a surface-owned native context menu. */
export type SurfaceMenuItem = { id: string; label: string };

/** Identifies one surface: a plugin may own more than one. */
export type SurfaceKey = { pluginId: string; surfaceId: string };

/** Channel the host pushes a surface's resolved anchor on after every move. */
export const surfacePositionChannel = "desktop:surface-position";
/** Channel the host relays transient plugin-authored payloads to a surface renderer on. */
export const surfaceMessageChannel = "desktop:surface-message";
/** Channel carrying a surface's retained state, replayed whenever it reports ready. */
export const surfaceStateChannel = "desktop:surface-state";
/**
 * Channel carrying a settle to the plugin-host renderer (#181-C).
 *
 * Distinct from `surfacePositionChannel`, which goes to the surface's *own*
 * window so it can lay itself out. This one goes to the window running the
 * owning plugin's `app.background` code, which is what actually decides
 * whether a settle is worth persisting — `surfaceSettleReason` is only
 * meaningful there, and the surface renderer never needed it.
 */
export const surfaceSettledChannel = "desktop:surface-settled";

export class DesktopSurfaceError extends Error {}

type SurfaceRecord = {
  key: SurfaceKey;
  spec: SurfaceSpec;
  window: SurfaceWindowHandle;
  anchor: SurfacePoint;
  extension: SurfaceExtension;
  dragPointerOffset: SurfacePoint | null;
  dragTimer: TimerHandle | null;
  momentum: SurfaceMomentum | null;
  momentumConfig: SurfaceMomentumConfig;
  momentumStartedAtMs: number;
  momentumUpdatedAtMs: number;
  momentumTimer: TimerHandle | null;
  move: { from: SurfacePoint; to: SurfacePoint; startedAtMs: number; durationMs: number } | null;
  moveTimer: TimerHandle | null;
  /** Last value passed to `setState`, replayed on `markReady`. See `setState`. */
  retained: { payload: unknown } | null;
  /**
   * Whether the plugin wants this surface on screen.
   *
   * Tracked so a renderer reload cannot un-hide a surface: the reloaded
   * renderer calls `ready()` again, and `markReady` shows the window so a
   * surface never sits there blank. Without this flag that would resurrect a
   * surface the plugin had explicitly hidden.
   */
  visible: boolean;
  /** Whether the renderer has installed its listeners at least once. */
  ready: boolean;
};

/**
 * Creates and drives plugin-owned desktop windows without knowing what they
 * contain.
 *
 * Every method here is something only the Electron main process can do:
 * screen coordinates, native cursor tracking, and per-frame window bounds.
 * Everything domain-specific — what to draw, when to pop a panel open, where
 * to remember a position — belongs to the plugin, which reaches these
 * primitives over IPC. See `contract.ts` for why plugin code never runs in
 * this process.
 *
 * Drag following, release momentum and eased moves are host primitives rather
 * than plugin logic because each writes window bounds on an 8–16ms cadence; a
 * renderer driving them would cross the IPC boundary on every frame.
 */
export class DesktopSurfaceHost {
  private readonly surfaces = new Map<string, SurfaceRecord>();
  private readonly now: () => number;
  private readonly setTimer: (callback: () => void, delayMs: number) => TimerHandle;
  private readonly clearTimer: (handle: TimerHandle) => void;

  constructor(private readonly options: DesktopSurfaceHostOptions) {
    this.now = options.now ?? Date.now;
    this.setTimer = options.setTimer ?? ((callback, delayMs) => setTimeout(callback, delayMs));
    this.clearTimer = options.clearTimer ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  }

  /** Creates a surface and places its body at `anchor`, clamped into the work area. */
  create(key: SurfaceKey, spec: SurfaceSpec, anchor: SurfacePoint): SurfacePoint {
    const id = surfaceKeyId(key);
    const existing = this.surfaces.get(id);
    if (existing && !existing.window.isDestroyed()) {
      throw new DesktopSurfaceError(`surface ${id} 已存在`);
    }
    const window = this.options.createWindow(key, spec);
    const record: SurfaceRecord = {
      key,
      spec,
      window,
      anchor,
      extension: noSurfaceExtension,
      dragPointerOffset: null,
      dragTimer: null,
      momentum: null,
      momentumConfig: {},
      momentumStartedAtMs: 0,
      momentumUpdatedAtMs: 0,
      momentumTimer: null,
      move: null,
      moveTimer: null,
      retained: null,
      visible: true,
      ready: false,
    };
    this.surfaces.set(id, record);
    // A window closed by the OS (or by Electron shutting down) must not leave
    // timers running against a destroyed handle.
    window.onClosed(() => {
      if (this.surfaces.get(id) === record) this.forget(record);
    });
    if (spec.clickThrough) window.setIgnoreMouseEvents(true, { forward: true });
    const applied = this.applyAnchor(record, anchor);
    this.notifyPlacement(record, "create");
    return applied;
  }

  /**
   * Whether any plugin still has a live surface.
   *
   * The main window's close policy uses this: closing the shell must not quit
   * the app while a plugin still owns a desktop window the user can see. It
   * used to ask "is the desktop pet running", which meant the policy had to
   * know what a pet was — and would have been wrong for the second plugin to
   * own a surface.
   */
  hasAny(): boolean {
    for (const record of this.surfaces.values()) {
      if (!record.window.isDestroyed()) return true;
    }
    return false;
  }

  /** Returns whether the plugin's surface exists and is still alive. */
  has(key: SurfaceKey): boolean {
    const record = this.surfaces.get(surfaceKeyId(key));
    return Boolean(record && !record.window.isDestroyed());
  }

  /** Attributes an IPC sender's window to the surface that owns it, if any. */
  keyForWindowId(windowId: number | null | undefined): SurfaceKey | null {
    if (typeof windowId !== "number") return null;
    for (const record of this.surfaces.values()) {
      if (record.window.id === windowId && !record.window.isDestroyed()) return record.key;
    }
    return null;
  }

  destroy(key: SurfaceKey): void {
    const record = this.surfaces.get(surfaceKeyId(key));
    if (!record) return;
    this.forget(record);
    if (!record.window.isDestroyed()) record.window.destroy();
  }

  /**
   * Tears down every surface a plugin owns.
   *
   * This is what makes "disable the plugin and its window is gone" true rather
   * than aspirational: the host, not the plugin, holds the handles and the
   * timers, so reclaiming them cannot depend on disabled plugin code running.
   */
  destroyAllForPlugin(pluginId: string): void {
    for (const record of [...this.surfaces.values()]) {
      if (record.key.pluginId === pluginId) this.destroy(record.key);
    }
  }

  /**
   * Tears down every surface, whoever owns it.
   *
   * For the case where the process that owns *all* of them is gone: since
   * #181-C every surface is driven by plugin `app.background` code in the
   * plugin-host renderer, so that renderer crashing leaves each one a
   * frameless, always-on-top window with nobody left to move, hide or close
   * it — the user cannot get rid of it without killing the app. Reclaiming
   * them is the only safe response; the alternative is a window the user
   * cannot dismiss.
   */
  destroyAll(): void {
    for (const record of [...this.surfaces.values()]) this.destroy(record.key);
  }

  show(key: SurfaceKey): void {
    const record = this.require(key);
    record.visible = true;
    if (record.ready) record.window.showInactive();
  }

  hide(key: SurfaceKey): void {
    const record = this.require(key);
    record.visible = false;
    this.stopInteractions(record);
    record.window.hide();
  }

  /** Places the body anchor, clamped into the work area; returns where it landed. */
  setPosition(key: SurfaceKey, anchor: SurfacePoint): SurfacePoint {
    const record = this.require(key);
    this.stopInteractions(record);
    const applied = this.applyAnchor(record, anchor);
    this.notifyPlacement(record, "position");
    return applied;
  }

  /** Grows or shrinks the window on one side of the body without moving the body. */
  setExtension(key: SurfaceKey, extension: SurfaceExtension): void {
    const record = this.require(key);
    record.extension = extension;
    this.applyAnchor(record, record.anchor);
    this.notifyPlacement(record, "extension");
  }

  /** The work area of the display the surface currently sits on. */
  workArea(key: SurfaceKey): SurfaceWorkArea {
    const record = this.require(key);
    return this.options.workAreaFor(record.window);
  }

  /** Stable identity of the display the surface currently sits on. */
  displayId(key: SurfaceKey): string {
    const record = this.require(key);
    return this.options.displayIdFor?.(record.window) ?? "";
  }

  setClickThrough(key: SurfaceKey, clickThrough: boolean): void {
    this.require(key).window.setIgnoreMouseEvents(clickThrough, { forward: true });
  }

  /**
   * Relays a *transient* plugin-authored payload to its own surface renderer.
   *
   * Not retained: a renderer that mounts (or reloads) after this call will
   * never see it. Use it for one-shot events — "play this animation now" —
   * and `setState` for anything the surface must still be showing afterwards.
   */
  postMessage(key: SurfaceKey, payload: unknown): void {
    const record = this.surfaces.get(surfaceKeyId(key));
    if (!record || record.window.isDestroyed()) return;
    record.window.send(surfaceMessageChannel, payload);
  }

  /**
   * Sets the surface's *retained* state, replayed whenever it reports ready.
   *
   * A surface renderer mounts asynchronously and can reload at any time, so a
   * plugin that only pushed state once would leave a blank window behind. The
   * host holding the latest state means the plugin does not have to implement
   * a ready handshake — or remember it exists. This is the generic form of
   * what the desktop pet's `sendCurrentLoad` does by hand today.
   */
  setState(key: SurfaceKey, payload: unknown): void {
    const record = this.surfaces.get(surfaceKeyId(key));
    if (!record) return;
    record.retained = { payload };
    if (!record.window.isDestroyed()) record.window.send(surfaceStateChannel, payload);
  }

  /**
   * Handles a surface renderer announcing it has installed its listeners.
   *
   * Replays the retained state and the current placement, so the renderer
   * never has to ask for either, then re-asserts visibility — with
   * `showInactive`, so a surface never steals focus.
   *
   * `ready` gates explicit show requests during startup; `visible` preserves
   * the plugin's hide intent across reloads. The Electron adapter additionally
   * waits for the first paint before actually revealing the window.
   */
  markReady(key: SurfaceKey): void {
    const record = this.require(key);
    record.ready = true;
    if (record.retained) record.window.send(surfaceStateChannel, record.retained.payload);
    this.notifyPlacement(record, "ready");
    if (record.visible) record.window.showInactive();
  }

  /**
   * Opens a native context menu over the surface and resolves the chosen id.
   *
   * Native menus are a main-process capability; a renderer can only draw its
   * own DOM, which cannot escape a transparent window's bounds.
   */
  async showContextMenu(key: SurfaceKey, items: SurfaceMenuItem[]): Promise<string | null> {
    const record = this.require(key);
    const show = this.options.showContextMenu;
    if (!show || items.length === 0) return null;
    return await show(record.window, items);
  }

  /** Brings the main application window forward on the surface's behalf. */
  activateMainWindow(): void {
    this.options.activateMainWindow?.();
  }

  /**
   * Starts following the native cursor.
   *
   * `pointerOffset` is where inside the body the pointer grabbed, so the
   * surface keeps its position relative to the cursor instead of snapping its
   * corner to it.
   */
  beginDrag(key: SurfaceKey, pointerOffset: SurfacePoint): void {
    const record = this.require(key);
    this.stopInteractions(record);
    record.dragPointerOffset = pointerOffset;
    record.dragTimer = this.setTimer(() => this.followDrag(record), surfaceDragFollowIntervalMs);
  }

  /**
   * Stops following the cursor, optionally handing over a release velocity
   * (px/s) for the host to glide out.
   */
  endDrag(key: SurfaceKey, velocity?: SurfacePoint, config: SurfaceMomentumConfig = {}): void {
    const record = this.require(key);
    this.stopDrag(record);
    if (!velocity || (velocity.x === 0 && velocity.y === 0)) {
      this.notifyPlacement(record, "drag");
      return;
    }
    record.momentum = { position: record.anchor, velocity };
    record.momentumConfig = config;
    record.momentumStartedAtMs = this.now();
    record.momentumUpdatedAtMs = record.momentumStartedAtMs;
    record.momentumTimer = this.setTimer(() => this.advanceMomentum(record), surfaceMomentumIntervalMs);
  }

  /** Eases the surface to a target anchor over `durationMs`, cancelling any interaction. */
  moveTo(key: SurfaceKey, target: SurfacePoint, durationMs: number): void {
    const record = this.require(key);
    this.stopInteractions(record);
    if (durationMs <= 0) {
      this.applyAnchor(record, target);
      this.notifyPlacement(record, "move");
      return;
    }
    const workArea = this.options.workAreaFor(record.window);
    const to = clampSurfaceAnchor(target, record.spec.body, workArea);
    const from = record.anchor;
    if (from.x === to.x && from.y === to.y) return;
    record.move = { from, to, startedAtMs: this.now(), durationMs };
    record.moveTimer = this.setTimer(() => this.advanceMove(record), surfaceMoveFrameMs);
  }

  private followDrag(record: SurfaceRecord): void {
    record.dragTimer = null;
    const offset = record.dragPointerOffset;
    if (!offset || record.window.isDestroyed()) return;
    this.applyAnchor(record, surfaceAnchorFromCursor(this.options.cursorScreenPoint(), offset));
    record.dragTimer = this.setTimer(() => this.followDrag(record), surfaceDragFollowIntervalMs);
  }

  private advanceMomentum(record: SurfaceRecord): void {
    record.momentumTimer = null;
    const momentum = record.momentum;
    if (!momentum || record.window.isDestroyed()) {
      this.stopMomentum(record);
      return;
    }
    const now = this.now();
    const next = advanceSurfaceMomentum(momentum, now - record.momentumUpdatedAtMs, record.momentumConfig);
    record.momentumUpdatedAtMs = now;
    const applied = this.applyAnchor(record, next.position);
    // An axis that got clamped against a work-area edge has spent its velocity;
    // zeroing it per axis lets the surface keep sliding along the edge instead
    // of stopping dead in a corner. When both axes are clamped the resulting
    // zero speed makes `shouldStopSurfaceMomentum` settle the glide below.
    const velocity = { ...next.velocity };
    if (applied.x !== Math.round(next.position.x)) velocity.x = 0;
    if (applied.y !== Math.round(next.position.y)) velocity.y = 0;
    record.momentum = { position: applied, velocity };
    if (shouldStopSurfaceMomentum(record.momentum, now - record.momentumStartedAtMs, record.momentumConfig)) {
      this.stopMomentum(record);
      this.notifyPlacement(record, "momentum");
      return;
    }
    record.momentumTimer = this.setTimer(() => this.advanceMomentum(record), surfaceMomentumIntervalMs);
  }

  private advanceMove(record: SurfaceRecord): void {
    record.moveTimer = null;
    const move = record.move;
    if (!move || record.window.isDestroyed()) {
      record.move = null;
      return;
    }
    const progress = Math.min(1, Math.max(0, (this.now() - move.startedAtMs) / move.durationMs));
    const eased = 1 - (1 - progress) ** 3;
    this.applyAnchor(record, {
      x: move.from.x + (move.to.x - move.from.x) * eased,
      y: move.from.y + (move.to.y - move.from.y) * eased,
    });
    if (progress >= 1) {
      record.move = null;
      this.notifyPlacement(record, "move");
      return;
    }
    record.moveTimer = this.setTimer(() => this.advanceMove(record), surfaceMoveFrameMs);
  }

  /** Clamps, rounds and writes the window bounds. Deliberately silent — see `notifyPlacement`. */
  private applyAnchor(record: SurfaceRecord, anchor: SurfacePoint): SurfacePoint {
    const window = record.window;
    if (window.isDestroyed()) return record.anchor;
    const workArea = this.options.workAreaFor(window);
    const clamped = clampSurfaceAnchor(anchor, record.spec.body, workArea);
    const rounded = { x: Math.round(clamped.x), y: Math.round(clamped.y) };
    record.anchor = rounded;
    window.setBounds(surfaceWindowBounds(rounded, record.spec.body, record.extension));
    return rounded;
  }

  /**
   * Tells the surface renderer where it ended up, so the plugin can persist the
   * position and lay its content out without asking.
   *
   * Sent only when the surface *settles* — never from a drag, glide or tween
   * frame. Those write bounds every 8–16ms, and pushing an IPC message on each
   * one would recreate exactly the per-frame renderer round-trip these host
   * primitives exist to avoid. A renderer does not need screen coordinates
   * while the host is moving its window; it needs them once the motion stops.
   */
  private notifyPlacement(record: SurfaceRecord, reason: SurfaceSettleReason): void {
    const window = record.window;
    if (window.isDestroyed()) return;
    const placement: SurfacePlacementInfo = {
      anchor: record.anchor,
      bodyOffset: surfaceBodyOffset(record.extension),
      workArea: this.options.workAreaFor(window),
    };
    window.send(surfacePositionChannel, placement);
    try {
      this.options.onSettled?.(record.key, placement, reason);
    } catch {
      // An observer that throws must not take down the glide or tween timer
      // this can be called from, nor leave a surface mid-motion. Whoever
      // installs the observer owns reporting its own failures.
    }
  }

  /** Re-reads the anchor from the OS, for callers that suspect the window moved behind us. */
  anchorFromWindow(key: SurfaceKey): SurfacePoint {
    const record = this.require(key);
    if (record.window.isDestroyed()) return record.anchor;
    return surfaceAnchorFromWindowBounds(record.window.getBounds(), record.extension);
  }

  private stopInteractions(record: SurfaceRecord): void {
    this.stopDrag(record);
    this.stopMomentum(record);
    this.stopMove(record);
  }

  private stopDrag(record: SurfaceRecord): void {
    if (record.dragTimer !== null) this.clearTimer(record.dragTimer);
    record.dragTimer = null;
    record.dragPointerOffset = null;
  }

  private stopMomentum(record: SurfaceRecord): void {
    if (record.momentumTimer !== null) this.clearTimer(record.momentumTimer);
    record.momentumTimer = null;
    record.momentum = null;
  }

  private stopMove(record: SurfaceRecord): void {
    if (record.moveTimer !== null) this.clearTimer(record.moveTimer);
    record.moveTimer = null;
    record.move = null;
  }

  private forget(record: SurfaceRecord): void {
    this.stopInteractions(record);
    this.surfaces.delete(surfaceKeyId(record.key));
  }

  private require(key: SurfaceKey): SurfaceRecord {
    const record = this.surfaces.get(surfaceKeyId(key));
    if (!record || record.window.isDestroyed()) {
      throw new DesktopSurfaceError(`surface ${surfaceKeyId(key)} 不存在`);
    }
    return record;
  }
}

/** Flattens a surface key into the map key and the id used in error messages. */
export function surfaceKeyId(key: SurfaceKey): string {
  return `${key.pluginId}:${key.surfaceId}`;
}
