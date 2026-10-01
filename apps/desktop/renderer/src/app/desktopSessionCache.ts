import type { RoleRecord, SessionPayload } from "@shiori/sdk";
import { readRoleSessionCache, removeRoleSessionCache, retainRoleSessionCache, writeRoleSessionCache } from "../chat/roleSessionCache";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
type Args = Pick<DesktopSessionStateArgs, "roleSessionCacheRef">;
/** Keeps role snapshots available for immediate role switching. */
export function createDesktopSessionCache({
  roleSessionCacheRef
}: Args) {
  function cacheRoleSession(roleId: string, session: SessionPayload): void {
    roleSessionCacheRef.current = writeRoleSessionCache(roleSessionCacheRef.current, roleId, session);
  }

  function readCachedRoleSession(roleId: string): SessionPayload | null {
    return readRoleSessionCache(roleSessionCacheRef.current, roleId);
  }

  function removeCachedRoleSession(roleId: string): void {
    roleSessionCacheRef.current = removeRoleSessionCache(roleSessionCacheRef.current, roleId);
  }

  function retainCachedRoleSessions(nextRoles: readonly RoleRecord[]): void {
    roleSessionCacheRef.current = retainRoleSessionCache(
      roleSessionCacheRef.current,
      nextRoles.map((role) => role.id),
    );
  }

  return { cacheRoleSession, readCachedRoleSession, removeCachedRoleSession, retainCachedRoleSessions };
}
