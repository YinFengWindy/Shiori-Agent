import type { SurfaceKey } from "../surface/host.js";

/** Remaining pet/voice coupling; voice host capability injection belongs to #221. */
export const desktopPetPluginId = "desktop_pet";

/** Identifies the pet's window to the DesktopSurface capability. */
export const desktopPetSurfaceKey: SurfaceKey = { pluginId: desktopPetPluginId, surfaceId: "pet" };

/**
 * The pet's state as far as the host is concerned.
 *
 * Two facts, both for features that are not plugins yet: `visible` gates voice
 * admission (`voice/availability.ts`) and `roleId` says whose turn a voice
 * press belongs to. `available` used to be here too,
 * for the tray item's enabled state — that left with #181-D.
 */
export type DesktopPetPresence = {
  visible: boolean;
  roleId: string | null;
};

export const noDesktopPetPresence: DesktopPetPresence = {
  visible: false,
  roleId: null,
};

/**
 * Reads the three fields the host needs out of the pet's own store blob.
 *
 * Reading a plugin's private data is not a pattern to copy. It is here because
 * the alternative during the migration is worse: a second, host-only channel
 * carrying the same three facts, which would then have to be kept in step with
 * the plugin's own writes and would outlive the coupling it exists for. The
 * store already updates on every write the plugin makes, and everything below
 * is defensive about what it finds, so a plugin that changed its own format
 * degrades to "no pet" rather than to a crash.
 */
export function readDesktopPetPresence(stored: unknown): DesktopPetPresence {
  if (!stored || typeof stored !== "object") return noDesktopPetPresence;
  const source = stored as { visible?: unknown; roleId?: unknown; packageId?: unknown };
  const roleId = typeof source.roleId === "string" && source.roleId ? source.roleId : null;
  // A stored `visible` only counts when there is something to show. The plugin
  // normalizes this too, but the host reads the file the plugin wrote, and a
  // hand-edited one would otherwise admit voice input for a pet that cannot
  // exist.
  const bound = Boolean(roleId && typeof source.packageId === "string" && source.packageId);
  return {
    visible: source.visible === true && bound,
    roleId,
  };
}

/**
 * Whether two presences differ in anything the host reacts to.
 *
 * Position writes do not change voice admission; only the visible role matters.
 */
export function desktopPetPresenceChanged(
  before: DesktopPetPresence,
  after: DesktopPetPresence,
): boolean {
  return before.visible !== after.visible || before.roleId !== after.roleId;
}

/** Whether an IPC sender's window is the pet's surface. */
export function isDesktopPetWindow(
  surfaces: { keyForWindowId(windowId: number | null | undefined): SurfaceKey | null },
  window: { readonly id: number } | null,
): boolean {
  const key = surfaces.keyForWindowId(window?.id);
  return Boolean(
    key
    && key.pluginId === desktopPetSurfaceKey.pluginId
    && key.surfaceId === desktopPetSurfaceKey.surfaceId,
  );
}
