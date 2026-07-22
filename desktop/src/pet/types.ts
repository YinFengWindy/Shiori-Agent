/** Runtime state supported by the Codex-compatible sprite atlas. */
export type DesktopPetState =
  | "idle"
  | "running-right"
  | "running-left"
  | "waving"
  | "jumping"
  | "failed"
  | "waiting"
  | "running"
  | "review";

/** One validated role-owned pet package available to the desktop shell. */
export type DesktopPetPackage = {
  id: string;
  displayName: string;
  /** Opaque trusted local-asset URL, never a renderer-visible filesystem path. */
  spritesheetUrl: string;
};

/** Resolved binding used to load one desktop pet window. */
export type DesktopPetBinding = {
  roleId: string;
  package: DesktopPetPackage;
};

export type DesktopPetPosition = { x: number; y: number };

/** Persisted application-level desktop-pet configuration. */
export type DesktopPetSettings = {
  enabled: boolean;
  roleId: string | null;
  packageId: string | null;
  positions: Record<string, DesktopPetPosition>;
};

export const defaultDesktopPetSettings: DesktopPetSettings = {
  enabled: false,
  roleId: null,
  packageId: null,
  positions: {},
};
