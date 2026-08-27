import type { RoleRecord } from "../shared/types";

/**
 * Reconciles the bridge-provided role list against the current renderer state.
 * Only roles still present in the latest bridge response remain visible.
 */
export function reconcileRoles(current: RoleRecord[], incoming: RoleRecord[]): RoleRecord[] {
  const currentById = new Map<string, RoleRecord>();
  current.forEach((role) => {
    currentById.set(role.id, role);
  });

  return incoming.map((role) => {
    const existing = currentById.get(role.id);
    if (!existing) {
      return role;
    }
    const existingTime = Date.parse(existing.updated_at || existing.created_at || "");
    const incomingTime = Date.parse(role.updated_at || role.created_at || "");
    if (Number.isNaN(existingTime) || Number.isNaN(incomingTime) || incomingTime >= existingTime) {
      return role;
    }
    return existing;
  });
}
