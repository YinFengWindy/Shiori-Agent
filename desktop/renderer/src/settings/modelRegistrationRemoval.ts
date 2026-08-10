import type { ModelRegistrationFormData, PendingRoleModelUpdate } from "../../../src/shared";
import type { RoleRecord } from "../shared/types";

/** Confirms a registration removal and migrates role references before deletion. */
export async function prepareModelRegistrationRemoval(
  registration: ModelRegistrationFormData,
  registrations: ModelRegistrationFormData[],
): Promise<PendingRoleModelUpdate[] | null> {
  if (registrations.length <= 1) return null;
  const response = await window.miraDesktop.invoke({ method: "roles.list", payload: {} });
  if (response.error) {
    window.alert(response.error.message);
    return null;
  }
  const roles = Array.isArray(response.payload.roles) ? response.payload.roles as RoleRecord[] : [];
  const affectedRoles = roles.filter((role) => (
    role.runtime_config.dialogue_model_registration_id === registration.id
    || role.runtime_config.visual_model_registration_id === registration.id
  ));
  const impact = affectedRoles.length > 0
    ? `\n受影响角色：${affectedRoles.map((role) => role.name).join("、")}`
    : "";
  if (!window.confirm(`删除模型注册“${registration.model}”？${impact}`)) return null;

  const fallbackId = registrations.find((item) => item.id !== registration.id)?.id ?? "";
  return affectedRoles.map((role) => ({
    roleId: role.id,
    runtimeConfig: {
      ...role.runtime_config,
      dialogue_model_registration_id: role.runtime_config.dialogue_model_registration_id === registration.id
        ? fallbackId
        : role.runtime_config.dialogue_model_registration_id,
      visual_model_registration_id: role.runtime_config.visual_model_registration_id === registration.id
        ? ""
        : role.runtime_config.visual_model_registration_id,
    },
  }));
}
