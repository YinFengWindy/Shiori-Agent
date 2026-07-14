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
    autoSceneCgEnabled: Boolean(role.runtime_config?.auto_scene_cg_enabled),
    channelBindings: role.channel_bindings ?? [],
    proactiveEnabled: role.proactive?.enabled ?? false,
    proactiveTargetChannel: role.proactive?.target_channel ?? "",
    proactiveTargetChatId: role.proactive?.target_chat_id ?? "",
    proactiveProfile: role.proactive?.profile ?? "daily",
    proactiveAgentModel: role.proactive?.agent?.model ?? "",
    proactiveAgentMaxSteps: role.proactive?.agent?.max_steps ?? 35,
    proactiveAgentContentLimit: role.proactive?.agent?.content_limit ?? 5,
    proactiveAgentWebFetchMaxChars: role.proactive?.agent?.web_fetch_max_chars ?? 8000,
    proactiveDriftEnabled: role.proactive?.drift?.enabled ?? false,
    proactiveDriftMaxSteps: role.proactive?.drift?.max_steps ?? 20,
    proactiveDriftMinIntervalHours: role.proactive?.drift?.min_interval_hours ?? 3,
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
        || roleForm.autoSceneCgEnabled !== Boolean(role.runtime_config?.auto_scene_cg_enabled)
        || JSON.stringify(roleForm.channelBindings ?? []) !== JSON.stringify(role.channel_bindings ?? [])
        || Boolean(roleForm.proactiveEnabled) !== Boolean(role.proactive?.enabled)
        || (roleForm.proactiveTargetChannel ?? "") !== (role.proactive?.target_channel ?? "")
        || (roleForm.proactiveTargetChatId ?? "") !== (role.proactive?.target_chat_id ?? "")
        || (roleForm.proactiveProfile ?? "daily") !== (role.proactive?.profile ?? "daily")
        || (roleForm.proactiveAgentModel ?? "") !== (role.proactive?.agent?.model ?? "")
        || (roleForm.proactiveAgentMaxSteps ?? 35) !== (role.proactive?.agent?.max_steps ?? 35)
        || (roleForm.proactiveAgentContentLimit ?? 5) !== (role.proactive?.agent?.content_limit ?? 5)
        || (roleForm.proactiveAgentWebFetchMaxChars ?? 8000) !== (role.proactive?.agent?.web_fetch_max_chars ?? 8000)
        || Boolean(roleForm.proactiveDriftEnabled) !== Boolean(role.proactive?.drift?.enabled)
        || (roleForm.proactiveDriftMaxSteps ?? 20) !== (role.proactive?.drift?.max_steps ?? 20)
        || (roleForm.proactiveDriftMinIntervalHours ?? 3) !== (role.proactive?.drift?.min_interval_hours ?? 3)
        || !roleMoodConfigEqual(roleForm, persistedMoodConfig)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
      )
  );
}
