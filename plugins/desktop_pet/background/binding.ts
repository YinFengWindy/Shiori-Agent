import { isRecord, nonempty, readPetModelReference, type PetBinding } from "@yinfengwindy/shiori-pet";
/** Reads only provider-neutral binding data; missing providers are backend errors. */
export function readDesktopPetBinding(value: unknown): PetBinding | null {
  if (!isRecord(value)) throw new Error("桌宠绑定响应无效");
  if (value.binding === null) return null;
  const binding = value.binding;
  if (!isRecord(binding) || !nonempty(binding.role_id) || !isRecord(binding.model)) throw new Error("桌宠绑定无效");
  const model = binding.model;
  const reference = readPetModelReference({ provider: binding.provider, model_id: model.id });
  if (!reference || !nonempty(model.display_name) || !isRecord(model.body) || typeof model.body.width !== "number" || typeof model.body.height !== "number" || !Number.isFinite(model.body.width) || !Number.isFinite(model.body.height) || model.body.width <= 0 || model.body.height <= 0 || !Array.isArray(model.actions) || !model.actions.every(nonempty)) throw new Error("桌宠模型描述无效");
  return { role_id: binding.role_id, provider: reference.provider, model: { id: reference.model_id, display_name: model.display_name, body: { width: model.body.width, height: model.body.height }, actions: model.actions, ...(typeof model.preview_abs === "string" ? { preview_abs: model.preview_abs } : {}) } };
}
