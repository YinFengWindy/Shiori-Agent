import type { RoleRecord } from "@shiori/plugin-sdk";
import { reconcileRoles } from "../roles/roleListState";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { createDesktopSessionCache } from "./desktopSessionCache";
type Args = Pick<DesktopSessionStateArgs, "setRoles" | "setUnreadCounts" | "feedback">
  & Pick<ReturnType<typeof createDesktopSessionCache>, "retainCachedRoleSessions">;
/** Refreshes role records and prunes unread counts and cached sessions. */
export function createDesktopRoleList({
  setRoles,
  setUnreadCounts,
  feedback,
  retainCachedRoleSessions
}: Args) {
  async function loadRolesFromBridge(): Promise<RoleRecord[] | null> {
    const rolesRes = await window.miraDesktop.invoke({
      method: "roles.list",
      payload: {},
    });
    if (rolesRes.error) {
      feedback.error(`角色列表加载失败：${rolesRes.error.message}`);
      return null;
    }
    const nextRoles = (rolesRes.payload.roles as RoleRecord[]) ?? [];
    let mergedRoles = nextRoles;
    setRoles((current) => {
      mergedRoles = reconcileRoles(current, nextRoles);
      return mergedRoles;
    });
    setUnreadCounts((current) => {
      const next: Record<string, number> = {};
      nextRoles.forEach((role) => {
        if (current[role.id]) {
          next[role.id] = current[role.id];
        }
      });
      return next;
    });
    retainCachedRoleSessions(nextRoles);
    return mergedRoles;
  }

  return { loadRolesFromBridge };
}
