import { isRecord } from "../provider/guards";
import { readPetModelReference, type PetModelReference } from "../provider";
import type { DesktopPetBinding, DesktopPetSettings } from "./types";
/** Reads device preferences and upgrades the old sprite selection mirror in memory. */
export function normalizeDesktopPetSettings(value: unknown): DesktopPetSettings {
  const source = isRecord(value) ? value : {};
  const roleId = typeof source.roleId === "string" && source.roleId.trim() ? source.roleId.trim() : null;
  const legacy: PetModelReference | null = typeof source.packageId === "string" && source.packageId.trim() ? { provider: { plugin_id: "pet_codex_sprite", service_id: "models" }, model_id: source.packageId.trim() } : null;
  const model = readPetModelReference(source.model) ?? legacy;
  const positions: DesktopPetSettings["positions"] = {};
  if (isRecord(source.positions)) for (const [key, position] of Object.entries(source.positions)) {
    if (isRecord(position) && typeof position.x === "number" && Number.isFinite(position.x) && typeof position.y === "number" && Number.isFinite(position.y)) positions[key] = { x: position.x, y: position.y };
  }
  return { visible: Boolean(source.visible ?? source.enabled) && Boolean(roleId && model), roleId, model, positions };
}
/** Patches selection without overwriting positions changed while a model was loading. */
export function desktopPetBindingPatch(binding: DesktopPetBinding, visible: boolean): Pick<DesktopPetSettings, "visible" | "roleId" | "model"> {
  return { visible, roleId: binding.role_id, model: { provider: binding.provider, model_id: binding.model.id } };
}
