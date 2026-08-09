import type { ModelRegistrationFormData } from "../../../src/shared";
import type { RoleRecord } from "../shared/types";

/** Confirms a registration removal and migrates role references before deletion. */
export async function prepareModelRegistrationRemoval(
  registration: ModelRegistrationFormData,
  registrations: ModelRegistrationFormData[],
): Promise<boolean> {
  if (registrations.length <= 1) return false;
  const response = await window.miraDesktop.invoke({ method: "roles.list", payload: {} });
  if (response.error) {
    window.alert(response.error.message);
    return false;
  }
  const roles = Array.isArray(response.payload.roles) ? response.payload.roles as RoleRecord[] : [];
  const affectedRoles = roles.filter((role) => (
    role.runtime_config.dialogue_model_registration_id === registration.id
    || role.runtime_config.visual_model_registration_id === registration.id
  ));
  const impact = affectedRoles.length > 0
    ? `\n受影响角色：${affectedRoles.map((role) => role.name).join("、")}`
    : "";
  if (!window.confirm(`删除模型注册“${registration.model}”？${impact}`)) return false;

  const fallbackId = registrations.find((item) => item.id !== registration.id)?.id ?? "";
  try {
    await Promise.all(affectedRoles.map(async (role) => {
      const runtimeConfig = {
        ...role.runtime_config,
        dialogue_model_registration_id: role.runtime_config.dialogue_model_registration_id === registration.id
          ? fallbackId
          : role.runtime_config.dialogue_model_registration_id,
        visual_model_registration_id: role.runtime_config.visual_model_registration_id === registration.id
          ? ""
          : role.runtime_config.visual_model_registration_id,
      };
      const updateResponse = await window.miraDesktop.invoke({
        method: "roles.update",
        payload: { role_id: role.id, runtime_config: runtimeConfig },
      });
      if (updateResponse.error) throw new Error(updateResponse.error.message);
    }));
  } catch (error) {
    window.alert(error instanceof Error ? error.message : String(error));
    return false;
  }
  return true;
}
