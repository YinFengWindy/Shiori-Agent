import { readPluginRoleSettings, pluginRoleSettingsDirty } from "../plugins/pluginRoleSettings";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { readRoleMoodConfig, roleMoodConfigEqual } from "./roleMoodConfig";
import { readRoleVoiceConfig, roleVoiceConfigEqual } from "./roleVoiceConfig";
import {
  buildRoleProactiveConfig as buildProactiveConfig,
  readRoleProactiveForm,
  roleProactiveConfigEqual,
} from "./roleProactiveDefaults";

/** Builds a proactive update while preserving persisted fields outside the form. */
export function buildRoleProactiveConfig(
  role: RoleRecord | null,
  roleForm: RoleFormState,
): ReturnType<typeof buildProactiveConfig> {
  return buildProactiveConfig(role, roleForm);
}

/** Builds the editable role form state from a persisted role snapshot. */
export function createRoleFormFromRole(role: RoleRecord): RoleFormState {
  const moodConfig = readRoleMoodConfig(role);
  const voiceConfig = readRoleVoiceConfig(role);
  return {
    name: role.name,
    description: role.description,
    systemPrompt: role.system_prompt,
    profile: role.profile,
    nsfwMemoryEnabled: Boolean(role.runtime_config?.nsfw_memory_enabled),
    pluginSettings: readPluginRoleSettings(role.runtime_config, role.plugin_state),
    channelBindings: [],
    ...readRoleProactiveForm(role),
    avatarSource: "",
    illustrationSources: [],
    removedIllustrations: [],
    moodCatalog: moodConfig.moodCatalog,
    defaultMood: moodConfig.defaultMood,
    moodIllustrationBindings: moodConfig.moodIllustrationBindings,
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
        || JSON.stringify(roleForm.profile ?? {}) !== JSON.stringify(role.profile ?? {})
        || roleForm.nsfwMemoryEnabled !== Boolean(role.runtime_config?.nsfw_memory_enabled)
        || pluginRoleSettingsDirty(roleForm.pluginSettings, role.runtime_config, role.plugin_state)
        || !roleProactiveConfigEqual(roleForm, role)
        || !roleMoodConfigEqual(roleForm, persistedMoodConfig)
        || !roleVoiceConfigEqual(roleForm, persistedVoiceConfig)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
        || roleForm.pendingVoiceAssetDeletes.length > 0
      )
  );
}
