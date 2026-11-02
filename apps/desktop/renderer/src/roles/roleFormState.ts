import { readPluginRoleSettings, pluginRoleSettingsDirty, writePluginRoleSettings } from "../plugins/pluginRoleSettings";
import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
import type { RoleFormState } from "../shared/types";
import { readRoleMoodConfig, roleMoodConfigEqual, writeRoleMoodConfigToRuntimeConfig } from "./roleMoodConfig";

/** Builds the runtime settings shared by role saves and mood-asset updates. */
export function buildRoleRuntimeConfig(role: RoleRecord | null, roleForm: RoleFormState) {
  return writeRoleMoodConfigToRuntimeConfig({
    ...writePluginRoleSettings(role?.runtime_config ?? {}, roleForm.pluginSettings),
    nsfw_memory_enabled: roleForm.nsfwMemoryEnabled,
    natural_chat_enabled: roleForm.naturalChatEnabled,
  }, roleForm);
}

/** Builds the editable role form state from a persisted role snapshot. */
export function createRoleFormFromRole(role: RoleRecord): RoleFormState {
  const moodConfig = readRoleMoodConfig(role);
  return {
    name: role.name,
    description: role.description,
    systemPrompt: role.system_prompt,
    profile: role.profile,
    nsfwMemoryEnabled: Boolean(role.runtime_config?.nsfw_memory_enabled),
    naturalChatEnabled: role.runtime_config?.natural_chat_enabled === true,
    pluginSettings: readPluginRoleSettings(role.runtime_config, role.plugin_state),
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
        || JSON.stringify(roleForm.profile ?? {}) !== JSON.stringify(role.profile ?? {})
        || roleForm.nsfwMemoryEnabled !== Boolean(role.runtime_config?.nsfw_memory_enabled)
        || roleForm.naturalChatEnabled !== (role.runtime_config?.natural_chat_enabled === true)
        || pluginRoleSettingsDirty(roleForm.pluginSettings, role.runtime_config, role.plugin_state)
        || !roleMoodConfigEqual(roleForm, persistedMoodConfig)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
      )
  );
}
