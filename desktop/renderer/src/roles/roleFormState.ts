import type { RoleFormState, RoleRecord } from "../shared/types";
import { readRoleMoodConfig, roleMoodConfigEqual } from "./roleMoodConfig";

/** Builds the editable role form state from a persisted role snapshot. */
export function createRoleFormFromRole(role: RoleRecord): RoleFormState {
  const moodConfig = readRoleMoodConfig(role);
  return {
    name: role.name,
    description: role.description,
    systemPrompt: role.system_prompt,
    nsfwMemoryEnabled: Boolean(role.runtime_config?.nsfw_memory_enabled),
    channelBindings: role.channel_bindings ?? [],
    proactiveEnabled: role.proactive?.enabled ?? false,
    proactiveTargetChannel: role.proactive?.target_channel ?? "",
    proactiveTargetChatId: role.proactive?.target_chat_id ?? "",
    avatarSource: "",
    illustrationSources: [],
    removedIllustrations: [],
    moodCatalog: moodConfig.moodCatalog,
    defaultMood: moodConfig.defaultMood,
    moodIllustrationBindings: moodConfig.moodIllustrationBindings,
  };
}

/** Checks whether the editable role form has diverged from the persisted role snapshot. */
export function isRoleFormDirty(roleForm: RoleFormState, role: RoleRecord | null): boolean {
  const persistedMoodConfig = readRoleMoodConfig(role);
  return Boolean(
    role
      && (
        roleForm.name !== role.name
        || roleForm.description !== role.description
        || roleForm.systemPrompt !== role.system_prompt
        || roleForm.nsfwMemoryEnabled !== Boolean(role.runtime_config?.nsfw_memory_enabled)
        || JSON.stringify(roleForm.channelBindings ?? []) !== JSON.stringify(role.channel_bindings ?? [])
        || Boolean(roleForm.proactiveEnabled) !== Boolean(role.proactive?.enabled)
        || (roleForm.proactiveTargetChannel ?? "") !== (role.proactive?.target_channel ?? "")
        || (roleForm.proactiveTargetChatId ?? "") !== (role.proactive?.target_chat_id ?? "")
        || !roleMoodConfigEqual(roleForm, persistedMoodConfig)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
      )
  );
}
