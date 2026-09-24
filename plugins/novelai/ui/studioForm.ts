import type { SelectOption } from "../../../apps/desktop/renderer/src/shared/ui/Select";
import type { ImageStudioFormState } from "./types";

/** Upper bound of one custom side; the total is capped by `maxCustomPixels`. */
const maxCustomSide = 1024;
const maxCustomPixels = 1024 * 1024;

/** Size choices: a Chinese shape name plus the exact NovelAI dimensions. */
export const sizeOptions = [
  { value: "square", label: "方形 · 1024 × 1024", triggerLabel: "方形 1024 × 1024" },
  { value: "portrait", label: "竖图 · 832 × 1216", triggerLabel: "竖图 832 × 1216" },
  { value: "landscape", label: "横图 · 1216 × 832", triggerLabel: "横图 1216 × 832" },
  { value: "custom", label: "自定义" },
] satisfies SelectOption[];

/** NovelAI's undesired-content presets, in the order of their numeric ids. */
export const undesiredContentPresetOptions = [
  { value: "0", label: "不使用" },
  { value: "1", label: "轻度" },
  { value: "2", label: "重度" },
] satisfies SelectOption[];

function parsePositiveInteger(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return parsed > 0 ? parsed : null;
}

/** Keeps a custom side to digits, capped at the per-side maximum. */
export function clampCustomDimensionInput(value: string): string {
  const digits = value.replace(/[^\d]/g, "");
  if (!digits) return "";
  const parsed = Math.trunc(Number(digits));
  return parsed > 0 ? String(Math.min(maxCustomSide, parsed)) : "";
}

/** The mode follows the form: a reference image makes it img2img. */
export function resolveStudioMode(form: ImageStudioFormState): ImageStudioFormState["mode"] {
  return form.baseImagePath.trim() ? "img2img" : "txt2img";
}

/** A blocking problem with the current form, or "" (an incomplete custom size is not an error yet). */
export function validateStudioForm(form: ImageStudioFormState): string {
  if (form.sizePreset !== "custom") return "";
  const width = parsePositiveInteger(form.customWidth);
  const height = parsePositiveInteger(form.customHeight);
  if (width == null || height == null) return "";
  if (width * height > maxCustomPixels) return "自定义尺寸的总像素不能超过 1024 × 1024";
  return "";
}

/** Whether 生成 can be pressed for this form (independent of token readiness). */
export function canSubmitStudioForm(form: ImageStudioFormState): boolean {
  if (!form.prompt.trim() || validateStudioForm(form)) return false;
  if (form.sizePreset !== "custom") return true;
  return parsePositiveInteger(form.customWidth) != null && parsePositiveInteger(form.customHeight) != null;
}

/** The `plugin.novelai.generate` payload for this form and resolved model. */
export function buildGeneratePayload(form: ImageStudioFormState, model: string): Record<string, unknown> {
  const mode = resolveStudioMode(form);
  const custom = form.sizePreset === "custom";
  return {
    role_id: form.roleId,
    session_key: form.roleId ? `role:${form.roleId}` : "desktop:image-studio",
    prompt: form.prompt,
    mode,
    base_image_path: form.baseImagePath,
    strength: mode === "img2img" ? form.strength : undefined,
    noise: mode === "img2img" ? form.noise : undefined,
    negative_prompt: form.negativePrompt,
    size_preset: form.sizePreset,
    custom_width: custom ? parsePositiveInteger(form.customWidth) : undefined,
    custom_height: custom ? parsePositiveInteger(form.customHeight) : undefined,
    model,
  };
}

/** Picks the generation role: keep a still-existing choice, else the role open in chat, else the first. */
export function resolveStudioRoleId(currentRoleId: string, activeRoleId: string, roleIds: string[]): string {
  if (currentRoleId && roleIds.includes(currentRoleId)) return currentRoleId;
  if (activeRoleId && roleIds.includes(activeRoleId)) return activeRoleId;
  return roleIds[0] ?? "";
}
