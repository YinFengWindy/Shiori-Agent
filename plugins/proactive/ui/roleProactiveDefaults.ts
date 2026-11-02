import type { PluginRoleValues } from "@yinfengwindy/shiori-sdk";

/** Stable defaults shared by the existing proactive panel fields. */
export const roleProactiveDefaults = Object.freeze({
  enabled: false, profile: "daily", agentMaxSteps: 35, agentContentLimit: 5,
  agentWebFetchMaxChars: 8000, driftMaxSteps: 20, driftMinIntervalHours: 3,
});

/** Projects the plugin snapshot into the role editor's draft. */
export function readRoleProactiveForm(values: PluginRoleValues) {
  return {
    proactiveEnabled: values.proactiveEnabled === true,
    proactiveProfile: typeof values.proactiveProfile === "string" ? values.proactiveProfile : roleProactiveDefaults.profile,
    proactiveAgentMaxSteps: typeof values.proactiveAgentMaxSteps === "number" ? values.proactiveAgentMaxSteps : roleProactiveDefaults.agentMaxSteps,
    proactiveAgentContentLimit: typeof values.proactiveAgentContentLimit === "number" ? values.proactiveAgentContentLimit : roleProactiveDefaults.agentContentLimit,
    proactiveAgentWebFetchMaxChars: typeof values.proactiveAgentWebFetchMaxChars === "number" ? values.proactiveAgentWebFetchMaxChars : roleProactiveDefaults.agentWebFetchMaxChars,
    proactiveDriftMaxSteps: typeof values.proactiveDriftMaxSteps === "number" ? values.proactiveDriftMaxSteps : roleProactiveDefaults.driftMaxSteps,
    proactiveDriftMinIntervalHours: typeof values.proactiveDriftMinIntervalHours === "number" ? values.proactiveDriftMinIntervalHours : roleProactiveDefaults.driftMinIntervalHours,
  };
}

/** Editable values owned by the proactive plugin. */
export type RoleProactiveFormState = ReturnType<typeof readRoleProactiveForm>;
