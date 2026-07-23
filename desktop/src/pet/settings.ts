import { readFileSync } from "node:fs";
import { writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { defaultDesktopPetSettings, type DesktopPetBinding, type DesktopPetSettings } from "./types.js";

function asFiniteCoordinate(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Parses persisted desktop-pet data and normalizes unusable enable states. */
export function normalizeDesktopPetSettings(value: unknown): DesktopPetSettings {
  const source = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const roleId = typeof source.roleId === "string" && source.roleId.trim() ? source.roleId.trim() : null;
  const packageId = typeof source.packageId === "string" && source.packageId.trim() ? source.packageId.trim() : null;
  const positions: DesktopPetSettings["positions"] = {};
  if (source.positions && typeof source.positions === "object") {
    for (const [key, position] of Object.entries(source.positions as Record<string, unknown>)) {
      if (!position || typeof position !== "object") continue;
      const point = position as Record<string, unknown>;
      const x = asFiniteCoordinate(point.x);
      const y = asFiniteCoordinate(point.y);
      if (x !== null && y !== null) positions[key] = { x, y };
    }
  }
  return {
    visible: Boolean(source.visible ?? source.enabled) && Boolean(roleId && packageId),
    observationEnabled: Boolean(source.observationEnabled) && Boolean(roleId && packageId),
    roleId,
    packageId,
    positions,
  };
}

/** Replaces the single active role/package slot while retaining per-role window positions. */
export function bindDesktopPetSettings(
  settings: DesktopPetSettings,
  binding: DesktopPetBinding,
  visible: boolean,
): DesktopPetSettings {
  const bindingChanged = settings.roleId !== binding.roleId || settings.packageId !== binding.package.id;
  return {
    ...settings,
    visible,
    observationEnabled: bindingChanged ? false : settings.observationEnabled,
    roleId: binding.roleId,
    packageId: binding.package.id,
  };
}

/** Loads the local desktop-pet configuration without treating a missing file as an error. */
export function loadDesktopPetSettings(path: string): DesktopPetSettings {
  try {
    return normalizeDesktopPetSettings(JSON.parse(readFileSync(path, "utf-8")));
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT" || error instanceof SyntaxError) return defaultDesktopPetSettings;
    throw error;
  }
}

/** Atomically persists the already-normalized desktop-pet configuration. */
export async function saveDesktopPetSettings(path: string, settings: DesktopPetSettings): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(settings, null, 2)}\n`, "utf-8");
  await writeFile(path, `${JSON.stringify(settings, null, 2)}\n`, "utf-8");
}
