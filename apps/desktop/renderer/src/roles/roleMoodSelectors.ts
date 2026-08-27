import type { RoleFormState, RoleRecord, SessionPayload } from "../shared/types";

type ResolveCurrentMoodArgs = {
  activeSession: SessionPayload | null;
  detailRole: RoleRecord | null;
  roleForm: Pick<RoleFormState, "defaultMood">;
};

type ResolveMoodIllustrationArgs = {
  activeSession: SessionPayload | null;
  detailRole: RoleRecord | null;
  roleForm: Pick<RoleFormState, "defaultMood" | "moodIllustrationBindings">;
};

/** Reads the current chat mood from session metadata with role-form fallback. */
export function resolveCurrentMood({
  activeSession,
  detailRole,
  roleForm,
}: ResolveCurrentMoodArgs): string {
  const sessionMood = String(activeSession?.metadata.current_mood ?? "").trim();
  if (sessionMood) {
    return sessionMood;
  }
  const formDefaultMood = String(roleForm.defaultMood ?? "").trim();
  if (formDefaultMood) {
    return formDefaultMood;
  }
  const runtimeConfig = detailRole?.runtime_config ?? {};
  return String(runtimeConfig.default_mood ?? "").trim();
}

/** Resolves which illustration should represent the current mood in the chat sidebar. */
export function resolveMoodIllustration({
  activeSession,
  detailRole,
  roleForm,
}: ResolveMoodIllustrationArgs): string {
  const runtimeConfig = detailRole?.runtime_config ?? {};
  const currentMood = resolveCurrentMood({
    activeSession,
    detailRole,
    roleForm,
  });
  const bindings = normalizeMoodBindings({
    ...(runtimeConfig.mood_illustration_bindings as Record<string, unknown> | undefined),
    ...roleForm.moodIllustrationBindings,
  });
  const selectedBinding = bindings[currentMood] || "";
  if (!selectedBinding) {
    return "";
  }
  return resolveIllustrationAssetPath(selectedBinding, detailRole) || selectedBinding;
}

/** Returns whether the current mood maps to an explicit mood illustration binding. */
export function hasMoodIllustrationBinding({
  activeSession,
  detailRole,
  roleForm,
}: Pick<ResolveMoodIllustrationArgs, "activeSession" | "detailRole" | "roleForm">): boolean {
  const runtimeConfig = detailRole?.runtime_config ?? {};
  const currentMood = resolveCurrentMood({
    activeSession,
    detailRole,
    roleForm,
  });
  const bindings = normalizeMoodBindings({
    ...(runtimeConfig.mood_illustration_bindings as Record<string, unknown> | undefined),
    ...roleForm.moodIllustrationBindings,
  });
  return Boolean(currentMood && bindings[currentMood]);
}

function normalizeMoodBindings(bindings: Record<string, unknown> | undefined): Record<string, string> {
  if (!bindings) {
    return {};
  }
  const next: Record<string, string> = {};
  Object.entries(bindings).forEach(([key, value]) => {
    const mood = String(key ?? "").trim();
    const illustration = String(value ?? "").trim();
    if (!mood || !illustration) {
      return;
    }
    next[mood] = illustration;
  });
  return next;
}

function resolveIllustrationAssetPath(
  illustrationPath: string,
  detailRole: Pick<RoleRecord, "illustrations" | "illustrations_abs"> | null,
): string {
  if (!detailRole) {
    return "";
  }
  const illustrationIndex = detailRole.illustrations.findIndex((path) => path === illustrationPath);
  if (illustrationIndex < 0) {
    return "";
  }
  return detailRole.illustrations_abs[illustrationIndex] ?? "";
}
