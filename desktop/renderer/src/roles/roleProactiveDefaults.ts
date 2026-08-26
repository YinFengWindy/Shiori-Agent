/** Stable defaults for the role-owned proactive editor contract. */
export const roleProactiveDefaults = Object.freeze({
  profile: "daily",
  agentMaxSteps: 35,
  agentContentLimit: 5,
  agentWebFetchMaxChars: 8000,
  driftMaxSteps: 20,
  driftMinIntervalHours: 3,
});
