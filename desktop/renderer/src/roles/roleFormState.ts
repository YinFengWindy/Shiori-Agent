import type { RoleFormState, RoleProactiveConfig, RoleRecord } from "../shared/types";
import { readRoleMoodConfig, roleMoodConfigEqual } from "./roleMoodConfig";
import { readRoleVoiceConfig, roleVoiceConfigEqual } from "./roleVoiceConfig";
import { roleProactiveDefaults } from "./roleProactiveDefaults";

/** Builds a proactive update while preserving persisted fields outside the form. */
export function buildRoleProactiveConfig(
  role: RoleRecord | null,
  roleForm: RoleFormState,
): RoleProactiveConfig {
  const persisted = role?.proactive;
  const persistedAgent = { ...(persisted?.agent ?? {}) } as Record<string, unknown>;
  delete persistedAgent.model;
  return {
    ...persisted,
    enabled: Boolean(roleForm.proactiveEnabled),
    target_channel: roleForm.proactiveTargetChannel ?? "",
    target_chat_id: roleForm.proactiveTargetChatId ?? "",
    profile: roleForm.proactiveProfile ?? roleProactiveDefaults.profile,
    agent: {
      ...persistedAgent,
      max_steps: roleForm.proactiveAgentMaxSteps ?? roleProactiveDefaults.agentMaxSteps,
      content_limit: roleForm.proactiveAgentContentLimit ?? roleProactiveDefaults.agentContentLimit,
      web_fetch_max_chars: roleForm.proactiveAgentWebFetchMaxChars ?? roleProactiveDefaults.agentWebFetchMaxChars,
    },
    drift: {
      ...(persisted?.drift ?? {}),
      enabled: Boolean(roleForm.proactiveDriftEnabled),
      max_steps: roleForm.proactiveDriftMaxSteps ?? roleProactiveDefaults.driftMaxSteps,
      min_interval_hours: roleForm.proactiveDriftMinIntervalHours ?? roleProactiveDefaults.driftMinIntervalHours,
    },
  };
}

/** Builds the editable role form state from a persisted role snapshot. */
export function createRoleFormFromRole(role: RoleRecord): RoleFormState {
  const moodConfig = readRoleMoodConfig(role);
  const voiceConfig = readRoleVoiceConfig(role);
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
    proactiveProfile: role.proactive?.profile ?? roleProactiveDefaults.profile,
    proactiveAgentMaxSteps: role.proactive?.agent?.max_steps ?? roleProactiveDefaults.agentMaxSteps,
    proactiveAgentContentLimit: role.proactive?.agent?.content_limit ?? roleProactiveDefaults.agentContentLimit,
    proactiveAgentWebFetchMaxChars: role.proactive?.agent?.web_fetch_max_chars ?? roleProactiveDefaults.agentWebFetchMaxChars,
    proactiveDriftEnabled: role.proactive?.drift?.enabled ?? false,
    proactiveDriftMaxSteps: role.proactive?.drift?.max_steps ?? roleProactiveDefaults.driftMaxSteps,
    proactiveDriftMinIntervalHours: role.proactive?.drift?.min_interval_hours ?? roleProactiveDefaults.driftMinIntervalHours,
    avatarSource: "",
    illustrationSources: [],
    removedIllustrations: [],
    moodCatalog: moodConfig.moodCatalog,
    defaultMood: moodConfig.defaultMood,
    moodIllustrationBindings: moodConfig.moodIllustrationBindings,
    desktopPetEnabled: Boolean(role.desktop_pet_enabled),
    voiceEnabled: voiceConfig.enabled,
    voiceProvider: voiceConfig.provider,
    voiceOwnership: voiceConfig.ownership,
    voiceId: voiceConfig.voiceId,
    voiceName: voiceConfig.voiceName,
    voiceSpeed: voiceConfig.speed,
    voiceMoodEmotions: voiceConfig.moodTtsEmotions,
    pendingVoiceAssetDeletes: [],
  };
}

/** Applies persisted mood settings without discarding unrelated in-progress form edits. */
export function syncRoleFormMoodConfig(
  roleForm: RoleFormState,
  role: Pick<RoleRecord, "runtime_config">,
): RoleFormState {
  const moodConfig = readRoleMoodConfig(role);
  return {
    ...roleForm,
    moodCatalog: moodConfig.moodCatalog,
    defaultMood: moodConfig.defaultMood,
    moodIllustrationBindings: moodConfig.moodIllustrationBindings,
  };
}

/** Checks whether the editable role form has diverged from the persisted role snapshot. */
export function isRoleFormDirty(roleForm: RoleFormState, role: RoleRecord | null): boolean {
  const persistedMoodConfig = readRoleMoodConfig(role);
  const persistedVoiceConfig = readRoleVoiceConfig(role);
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
        || (roleForm.proactiveProfile ?? roleProactiveDefaults.profile) !== (role.proactive?.profile ?? roleProactiveDefaults.profile)
        || (roleForm.proactiveAgentMaxSteps ?? roleProactiveDefaults.agentMaxSteps) !== (role.proactive?.agent?.max_steps ?? roleProactiveDefaults.agentMaxSteps)
        || (roleForm.proactiveAgentContentLimit ?? roleProactiveDefaults.agentContentLimit) !== (role.proactive?.agent?.content_limit ?? roleProactiveDefaults.agentContentLimit)
        || (roleForm.proactiveAgentWebFetchMaxChars ?? roleProactiveDefaults.agentWebFetchMaxChars) !== (role.proactive?.agent?.web_fetch_max_chars ?? roleProactiveDefaults.agentWebFetchMaxChars)
        || Boolean(roleForm.proactiveDriftEnabled) !== Boolean(role.proactive?.drift?.enabled)
        || (roleForm.proactiveDriftMaxSteps ?? roleProactiveDefaults.driftMaxSteps) !== (role.proactive?.drift?.max_steps ?? roleProactiveDefaults.driftMaxSteps)
        || (roleForm.proactiveDriftMinIntervalHours ?? roleProactiveDefaults.driftMinIntervalHours) !== (role.proactive?.drift?.min_interval_hours ?? roleProactiveDefaults.driftMinIntervalHours)
        || !roleMoodConfigEqual(roleForm, persistedMoodConfig)
        || Boolean(roleForm.desktopPetEnabled) !== Boolean(role.desktop_pet_enabled)
        || !roleVoiceConfigEqual(roleForm, persistedVoiceConfig)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
        || roleForm.pendingVoiceAssetDeletes.length > 0
      )
  );
}
