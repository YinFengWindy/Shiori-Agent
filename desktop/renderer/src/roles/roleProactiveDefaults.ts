import type { RoleFormState, RoleProactiveConfig, RoleRecord } from "../shared/types";

/** Stable defaults for the role-owned proactive editor contract. */
export const roleProactiveDefaults = Object.freeze({
  enabled: false,
  targetChannel: "",
  targetChatId: "",
  profile: "daily",
  agentMaxSteps: 35,
  agentContentLimit: 5,
  agentWebFetchMaxChars: 8000,
  driftEnabled: false,
  driftMaxSteps: 20,
  driftMinIntervalHours: 3,
});

export type RoleProactiveFormState = Pick<
  RoleFormState,
  | "proactiveEnabled"
  | "proactiveTargetChannel"
  | "proactiveTargetChatId"
  | "proactiveProfile"
  | "proactiveAgentMaxSteps"
  | "proactiveAgentContentLimit"
  | "proactiveAgentWebFetchMaxChars"
  | "proactiveDriftEnabled"
  | "proactiveDriftMaxSteps"
  | "proactiveDriftMinIntervalHours"
>;

/** Creates the proactive portion of a new role form with one shared default source. */
export function createDefaultRoleProactiveForm(): RoleProactiveFormState {
  return {
    proactiveEnabled: roleProactiveDefaults.enabled,
    proactiveTargetChannel: roleProactiveDefaults.targetChannel,
    proactiveTargetChatId: roleProactiveDefaults.targetChatId,
    proactiveProfile: roleProactiveDefaults.profile,
    proactiveAgentMaxSteps: roleProactiveDefaults.agentMaxSteps,
    proactiveAgentContentLimit: roleProactiveDefaults.agentContentLimit,
    proactiveAgentWebFetchMaxChars: roleProactiveDefaults.agentWebFetchMaxChars,
    proactiveDriftEnabled: roleProactiveDefaults.driftEnabled,
    proactiveDriftMaxSteps: roleProactiveDefaults.driftMaxSteps,
    proactiveDriftMinIntervalHours: roleProactiveDefaults.driftMinIntervalHours,
  };
}

/** Reads role-owned proactive settings while preserving sparse historical role semantics. */
export function readRoleProactiveForm(
  role: Pick<RoleRecord, "proactive">,
): RoleProactiveFormState {
  const proactive = role.proactive;
  return {
    proactiveEnabled: proactive?.enabled ?? roleProactiveDefaults.enabled,
    proactiveTargetChannel: proactive?.target_channel ?? roleProactiveDefaults.targetChannel,
    proactiveTargetChatId: proactive?.target_chat_id ?? roleProactiveDefaults.targetChatId,
    proactiveProfile: proactive?.profile ?? roleProactiveDefaults.profile,
    proactiveAgentMaxSteps: proactive?.agent?.max_steps ?? roleProactiveDefaults.agentMaxSteps,
    proactiveAgentContentLimit: proactive?.agent?.content_limit ?? roleProactiveDefaults.agentContentLimit,
    proactiveAgentWebFetchMaxChars: proactive?.agent?.web_fetch_max_chars ?? roleProactiveDefaults.agentWebFetchMaxChars,
    proactiveDriftEnabled: proactive?.drift?.enabled ?? roleProactiveDefaults.driftEnabled,
    proactiveDriftMaxSteps: proactive?.drift?.max_steps ?? roleProactiveDefaults.driftMaxSteps,
    proactiveDriftMinIntervalHours: proactive?.drift?.min_interval_hours ?? roleProactiveDefaults.driftMinIntervalHours,
  };
}

/** Builds a role proactive update while retaining persisted fields outside the editor. */
export function buildRoleProactiveConfig(
  role: Pick<RoleRecord, "proactive"> | null,
  roleForm: RoleProactiveFormState,
): RoleProactiveConfig {
  const persisted = role?.proactive;
  const persistedAgent = { ...(persisted?.agent ?? {}) } as Record<string, unknown>;
  delete persistedAgent.model;
  return {
    ...persisted,
    enabled: Boolean(roleForm.proactiveEnabled),
    target_channel: roleForm.proactiveTargetChannel ?? roleProactiveDefaults.targetChannel,
    target_chat_id: roleForm.proactiveTargetChatId ?? roleProactiveDefaults.targetChatId,
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

/** Compares editable proactive settings with a persisted role snapshot. */
export function roleProactiveConfigEqual(
  roleForm: RoleProactiveFormState,
  role: Pick<RoleRecord, "proactive"> | null,
): boolean {
  if (!role) {
    return true;
  }
  const persisted = role.proactive;
  return (
    Boolean(roleForm.proactiveEnabled) === Boolean(persisted?.enabled)
    && (roleForm.proactiveTargetChannel ?? roleProactiveDefaults.targetChannel)
      === (persisted?.target_channel ?? roleProactiveDefaults.targetChannel)
    && (roleForm.proactiveTargetChatId ?? roleProactiveDefaults.targetChatId)
      === (persisted?.target_chat_id ?? roleProactiveDefaults.targetChatId)
    && (roleForm.proactiveProfile ?? roleProactiveDefaults.profile)
      === (persisted?.profile ?? roleProactiveDefaults.profile)
    && (roleForm.proactiveAgentMaxSteps ?? roleProactiveDefaults.agentMaxSteps)
      === (persisted?.agent?.max_steps ?? roleProactiveDefaults.agentMaxSteps)
    && (roleForm.proactiveAgentContentLimit ?? roleProactiveDefaults.agentContentLimit)
      === (persisted?.agent?.content_limit ?? roleProactiveDefaults.agentContentLimit)
    && (roleForm.proactiveAgentWebFetchMaxChars ?? roleProactiveDefaults.agentWebFetchMaxChars)
      === (persisted?.agent?.web_fetch_max_chars ?? roleProactiveDefaults.agentWebFetchMaxChars)
    && Boolean(roleForm.proactiveDriftEnabled) === Boolean(persisted?.drift?.enabled)
    && (roleForm.proactiveDriftMaxSteps ?? roleProactiveDefaults.driftMaxSteps)
      === (persisted?.drift?.max_steps ?? roleProactiveDefaults.driftMaxSteps)
    && (roleForm.proactiveDriftMinIntervalHours ?? roleProactiveDefaults.driftMinIntervalHours)
      === (persisted?.drift?.min_interval_hours ?? roleProactiveDefaults.driftMinIntervalHours)
  );
}
