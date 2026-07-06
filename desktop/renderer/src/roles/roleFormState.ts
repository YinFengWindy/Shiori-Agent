import type { RoleFormState, RoleRecord } from "../shared/types";

/** Builds the editable role form state from a persisted role snapshot. */
export function createRoleFormFromRole(role: RoleRecord): RoleFormState {
  return {
    name: role.name,
    description: role.description,
    systemPrompt: role.system_prompt,
    nsfwMemoryEnabled: Boolean(role.runtime_config?.nsfw_memory_enabled),
    avatarSource: "",
    illustrationSources: [],
    removedIllustrations: [],
  };
}

/** Checks whether the editable role form has diverged from the persisted role snapshot. */
export function isRoleFormDirty(roleForm: RoleFormState, role: RoleRecord | null): boolean {
  return Boolean(
    role
      && (
        roleForm.name !== role.name
        || roleForm.description !== role.description
        || roleForm.systemPrompt !== role.system_prompt
        || roleForm.nsfwMemoryEnabled !== Boolean(role.runtime_config?.nsfw_memory_enabled)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
      )
  );
}
