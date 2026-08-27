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
    nsfwMemoryEnabled: Boolean(role.runtime_config?.nsfw_memory_enabled),
    autoSceneCgEnabled: Boolean(role.runtime_config?.auto_scene_cg_enabled),
    channelBindings: role.channel_bindings ?? [],
    ...readRoleProactiveForm(role),
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
        || !roleProactiveConfigEqual(roleForm, role)
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
