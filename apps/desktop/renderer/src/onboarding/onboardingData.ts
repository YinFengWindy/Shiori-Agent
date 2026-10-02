import { BridgeError, errorMessage } from "@shiori/sdk";
import type { DesktopApi, ModelRegistrationFormData } from "../../../src/bridge/shared";
import type { RoleRecord } from "@shiori/sdk";
import { modelCapacityError } from "../../../src/settingsContract.js";
import { isModelRegistrationComplete } from "../settings/modelRegistration";
import { saveSettingsPageData } from "../settings/settingsPersistence";

/** Loads authoritative data; failed bridge reads must never imply empty or complete state. */
export async function loadOnboardingData(api: Pick<DesktopApi, "readSettings" | "invoke">) {
  const [settings, response] = await Promise.all([
    api.readSettings(), api.invoke({ method: "roles.list", payload: {} }),
  ]);
  if (response.error) throw new BridgeError(response.error.message, response.error.code, response.error.details);
  if (!Array.isArray(response.payload.roles)) throw new Error("未能读取角色列表。");
  return { settings, roles: response.payload.roles as RoleRecord[] };
}

/** Applies a registration through the same settings transaction used by the catalog. */
export async function registerOnboardingModel(api: Pick<DesktopApi, "readSettings" | "saveSettings">, registration: ModelRegistrationFormData) {
  const capacityError = modelCapacityError(registration);
  if (capacityError) throw new Error(capacityError);
  if (!isModelRegistrationComplete(registration)) throw new Error("请补填模型连接和上下文窗口。");
  const snapshot = await api.readSettings();
  const registrations = snapshot.formData.models.registrations;
  const result = await saveSettingsPageData(api, {
    ...snapshot.formData,
    models: { registrations: [...registrations.filter((item) => item.id !== registration.id), registration] },
  }, { expectedGeneration: snapshot.generation, operationId: crypto.randomUUID() });
  if (!result.saveResult.ok) {
    const error = result.saveResult.error;
    throw new BridgeError(error?.message ?? "模型注册失败。", error?.code ?? "settings_save_failed", error?.details);
  }
  if (!result.snapshot) throw new BridgeError("模型已保存，但刷新失败，请重新加载设置确认。", "settings_refresh_failed", {
    detail: errorMessage(result.refreshError, { includeDetail: true }),
  });
  return result.snapshot;
}
