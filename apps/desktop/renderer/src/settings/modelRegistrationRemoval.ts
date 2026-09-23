import type { ModelRegistrationFormData, PendingRoleModelUpdate } from "../../../src/bridge/shared";
import type { RoleRecord } from "../shared/types";

/** What removing one model registration would do, shown to the user before it is applied. */
export type ModelRegistrationRemovalPlan = {
  registration: ModelRegistrationFormData;
  /** Names of roles whose dialogue or visual model points at this registration. */
  affectedRoleNames: string[];
  /** Staged unbinding for those roles; nothing selects another model implicitly. */
  updates: PendingRoleModelUpdate[];
};

/**
 * Works out which roles lose their model if `registration` is removed,
 * counting edits already staged in the settings draft. Nothing is persisted
 * here — the caller confirms with the user, then applies `updates` together
 * with the removal. Throws when the role list cannot be read.
 */
export async function planModelRegistrationRemoval(
  registration: ModelRegistrationFormData,
  pendingUpdates: PendingRoleModelUpdate[] = [],
): Promise<ModelRegistrationRemovalPlan> {
  const response = await window.miraDesktop.invoke({ method: "roles.list", payload: {} });
  if (response.error) throw new Error(response.error.message);
  const roles = Array.isArray(response.payload.roles) ? response.payload.roles as RoleRecord[] : [];
  const effectiveRoles = roles.map((role) => ({
    ...role,
    runtime_config: {
      ...role.runtime_config,
      ...pendingUpdates.find((update) => update.roleId === role.id)?.runtimeConfig,
    },
  }));
  const affectedRoles = effectiveRoles.filter((role) => (
    role.runtime_config.dialogue_model_registration_id === registration.id
    || role.runtime_config.visual_model_registration_id === registration.id
  ));

  return {
    registration,
    affectedRoleNames: affectedRoles.map((role) => role.name),
    updates: affectedRoles.map((role) => ({
      roleId: role.id,
      runtimeConfig: {
        dialogue_model_registration_id: role.runtime_config.dialogue_model_registration_id === registration.id
          ? ""
          : role.runtime_config.dialogue_model_registration_id,
        visual_model_registration_id: role.runtime_config.visual_model_registration_id === registration.id
          ? ""
          : role.runtime_config.visual_model_registration_id,
      },
    })),
  };
}

/** Confirmation copy for a removal plan: names the affected roles when there are any. */
export function describeModelRegistrationRemoval(plan: ModelRegistrationRemovalPlan): string {
  const model = plan.registration.model || "未命名模型";
  if (plan.affectedRoleNames.length === 0) return `“${model}” 删除后无法恢复。`;
  return `“${model}” 删除后，${plan.affectedRoleNames.join("、")} 将失去所绑定的模型，需要重新选择。`;
}
