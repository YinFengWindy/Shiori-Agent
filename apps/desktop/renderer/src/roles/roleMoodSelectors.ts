import type { RoleFormState, RoleRecord, SessionPayload } from "../shared/types";

type ResolveCurrentMoodArgs = {
  activeSession: SessionPayload | null;
  detailRole: RoleRecord | null;
  roleForm: Pick<RoleFormState, "defaultMood">;
  useRoleForm?: boolean;
};

type ResolveMoodIllustrationArgs = {
  activeSession: SessionPayload | null;
  detailRole: RoleRecord | null;
  roleForm: Pick<RoleFormState, "defaultMood" | "moodIllustrationBindings">;
  useRoleForm?: boolean;
};

/** Reads the current chat mood from session metadata with role-form fallback. */
export function resolveCurrentMood({
  activeSession,
  detailRole,
  roleForm,
  useRoleForm = true,
}: ResolveCurrentMoodArgs): string {
  const sessionMood = String(roleSession(activeSession, detailRole?.id)?.metadata.current_mood ?? "").trim();
  if (sessionMood) {
    return sessionMood;
  }
  const formDefaultMood = useRoleForm ? String(roleForm.defaultMood ?? "").trim() : "";
  if (formDefaultMood) {
    return formDefaultMood;
  }
  const runtimeConfig = detailRole?.runtime_config ?? {};
  return String(runtimeConfig.default_mood ?? "").trim();
}

/**
 * When the session's mood was last set (`current_mood_updated_at`), or empty
 * when the shown mood is not the session's own (a fallback default).
 */
export function resolveCurrentMoodUpdatedAt(session: SessionPayload | null, roleId: string | undefined): string {
  const metadata = roleSession(session, roleId)?.metadata;
  if (!String(metadata?.current_mood ?? "").trim()) return "";
  return String(metadata?.current_mood_updated_at ?? "").trim();
}

/** Ignores a previously selected role's session while a new session is loading. */
export function roleSession(session: SessionPayload | null, roleId: string | undefined) {
  if (!session || !roleId) return null;
  const sessionRole = session.metadata.role_id;
  return (sessionRole ? sessionRole === roleId : session.key === `role:${roleId}`) ? session : null;
}

/** Uses legacy relationship text only until the role has a formal turn thought. */
export function resolveCurrentThought(session: SessionPayload | null, role: RoleRecord | null) {
  const loadedSession = roleSession(session, role?.id);
  // Wait for the role's session before deciding whether an upgrade fallback is needed.
  if (!loadedSession) return "";
  const metadata = loadedSession.metadata;
  if (typeof metadata.current_thought === "string") return metadata.current_thought.trim();
  const legacy = metadata.relationship_snapshot ?? role?.relationship_snapshot;
  return typeof legacy?.role_self_view === "string" ? legacy.role_self_view.trim() : "";
}

/** Resolves which illustration should represent the current mood in the chat sidebar. */
export function resolveMoodIllustration({
  activeSession,
  detailRole,
  roleForm,
  useRoleForm = true,
}: ResolveMoodIllustrationArgs): string {
  const runtimeConfig = detailRole?.runtime_config ?? {};
  const currentMood = resolveCurrentMood({
    activeSession,
    detailRole,
    roleForm,
    useRoleForm,
  });
  const bindings = normalizeMoodBindings({
    ...(runtimeConfig.mood_illustration_bindings as Record<string, unknown> | undefined),
    ...(useRoleForm ? roleForm.moodIllustrationBindings : {}),
  });
  const selectedBinding = bindings[currentMood] || "";
  if (!selectedBinding) {
    return "";
  }
  return resolveIllustrationAssetPath(selectedBinding, detailRole) || selectedBinding;
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
