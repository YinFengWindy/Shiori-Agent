import type { DesktopApi, ModelRegistrationFormData } from "../../../src/bridge/shared";
import type { RoleRecord } from "../shared/types";
import { saveSettingsPageData } from "../settings/settingsPersistence";

/** Loads authoritative data; failed bridge reads must never imply empty or complete state. */
export async function loadOnboardingData(api: Pick<DesktopApi, "readSettings" | "invoke">) {
  const [settings, response] = await Promise.all([
    api.readSettings(), api.invoke({ method: "roles.list", payload: {} }),
  ]);
  if (response.error) throw new Error(response.error.message);
  if (!Array.isArray(response.payload.roles)) throw new Error("未能读取角色列表。");
  return { settings, roles: response.payload.roles as RoleRecord[] };
}

/** Applies a registration through the same settings transaction used by the catalog. */
export async function registerOnboardingModel(api: Pick<DesktopApi, "readSettings" | "saveSettings">, registration: ModelRegistrationFormData) {
  if (!registration.provider.trim() || !registration.model.trim()) throw new Error("服务商和模型不能为空。");
  const snapshot = await api.readSettings();
  const registrations = snapshot.formData.models.registrations;
  const result = await saveSettingsPageData(api, {
    ...snapshot.formData,
    models: { registrations: [...registrations.filter((item) => item.id !== registration.id), registration] },
  }, { expectedGeneration: snapshot.generation, operationId: crypto.randomUUID() });
  if (!result.saveResult.ok || !result.snapshot) throw new Error(result.saveResult.error?.message ?? "模型注册失败。");
  return result.snapshot;
}
