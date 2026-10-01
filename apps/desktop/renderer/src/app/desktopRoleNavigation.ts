import type React from "react";
import type { RoleRecord } from "@shiori/sdk";
import { resolveImmediateRoleSession } from "../chat/roleSessionCache";
import { fetchRoleSession } from "./desktopSessionProtocol";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { createDesktopSessionSnapshot } from "./desktopSessionSnapshot";
import type { createDesktopSessionCache } from "./desktopSessionCache";
import type { createDesktopRoleList } from "./desktopRoleList";
import type { useDesktopSessionPagination } from "./useDesktopSessionPagination";
type Args = Pick<DesktopSessionStateArgs, "activeRoleIdRef" | "activeSessionRef" | "openRoleRequestIdRef" | "rolesRef" | "unreadCountsRef" | "setActiveRoleId" | "setActiveIllustration" | "setSelectedAvatarAsset" | "setSelectedChatBackground" | "setUnreadCounts" | "feedback" | "mainViewRef">
  & Pick<ReturnType<typeof createDesktopSessionSnapshot>, "commitActiveSession">
  & Pick<ReturnType<typeof createDesktopSessionCache>, "readCachedRoleSession" | "cacheRoleSession">
  & ReturnType<typeof createDesktopRoleList>
  & Pick<ReturnType<typeof useDesktopSessionPagination>, "invalidateSessionPagination">
  & { latestCallbacks: React.MutableRefObject<Pick<DesktopSessionStateArgs, "applyRoleSnapshot" | "buildNavigationEntry" | "pushNavigationEntry" | "replaceNavigationEntry">> };
/** Opens role sessions with optimistic navigation and stale-request protection. */
export function createDesktopRoleNavigation({
  activeRoleIdRef,
  activeSessionRef,
  openRoleRequestIdRef,
  rolesRef,
  unreadCountsRef,
  setActiveRoleId,
  setActiveIllustration,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  setUnreadCounts,
  feedback,
  mainViewRef,
  latestCallbacks,
  invalidateSessionPagination,
  readCachedRoleSession,
  commitActiveSession,
  cacheRoleSession,
  loadRolesFromBridge
}: Args) {
  async function openRole(
    roleId: string,
    roleOverride: RoleRecord | null = null,
    options?: { recordHistory?: boolean; preserveCurrentSession?: boolean },
  ): Promise<boolean> {
    const currentSessionKey = activeSessionRef.current?.key ?? "";
    if (currentSessionKey) {
      invalidateSessionPagination(currentSessionKey);
    }
    const requestId = openRoleRequestIdRef.current + 1;
    openRoleRequestIdRef.current = requestId;
    const previousRoleId = activeRoleIdRef.current;
    const previousSession = activeSessionRef.current;
    const previousRole = previousRoleId
      ? rolesRef.current.find((item) => item.id === previousRoleId) ?? null
      : null;
    const switchingRole = activeRoleIdRef.current !== roleId;
    const previousUnreadCount = unreadCountsRef.current[roleId] ?? 0;
    const cachedSession = readCachedRoleSession(roleId);
    const immediateSession = resolveImmediateRoleSession({
      currentRoleId: activeRoleIdRef.current,
      nextRoleId: roleId,
      currentSession: activeSessionRef.current,
      cachedSession,
    });
    const role = roleOverride ?? rolesRef.current.find((item) => item.id === roleId) ?? null;
    const preserveCurrentSession = Boolean(options?.preserveCurrentSession && !cachedSession);
    if (role && !preserveCurrentSession) {
      latestCallbacks.current.applyRoleSnapshot(role, cachedSession);
    }
    if (!preserveCurrentSession && immediateSession !== activeSessionRef.current) {
      commitActiveSession(immediateSession);
    }
    const { error: sessionError, session } = await fetchRoleSession(roleId);
    if (openRoleRequestIdRef.current !== requestId) {
      return false;
    }
    if (!session) {
      if (switchingRole) {
        if (previousRole) {
          latestCallbacks.current.applyRoleSnapshot(previousRole, previousSession);
        } else {
          setActiveRoleId(previousRoleId);
          activeRoleIdRef.current = previousRoleId;
          setActiveIllustration("");
          setSelectedAvatarAsset("");
          setSelectedChatBackground("");
        }
        commitActiveSession(previousSession);
        if (previousUnreadCount > 0) {
          setUnreadCounts((current) => (
            current[roleId] === previousUnreadCount
              ? current
              : {
                  ...current,
                  [roleId]: previousUnreadCount,
                }
          ));
        }
      }
      feedback.error(`打开会话失败：${sessionError ?? "未知错误"}`);
      return false;
    }
    const latestRoles = await loadRolesFromBridge();
    if (openRoleRequestIdRef.current !== requestId) {
      return false;
    }
    cacheRoleSession(roleId, session);
    invalidateSessionPagination(session.key);
    setActiveRoleId(roleId);
    commitActiveSession(session);
    const resolvedRole = roleOverride
      ?? latestRoles?.find((item) => item.id === roleId)
      ?? rolesRef.current.find((item) => item.id === roleId)
      ?? null;
    if (resolvedRole) {
      latestCallbacks.current.applyRoleSnapshot(resolvedRole, session);
    } else {
      setActiveIllustration("");
      setSelectedAvatarAsset("");
      setSelectedChatBackground("");
    }
    if (options?.recordHistory !== false) {
      latestCallbacks.current.pushNavigationEntry(latestCallbacks.current.buildNavigationEntry({ kind: "chat" }, roleId));
    } else if (mainViewRef.current.kind === "chat") {
      latestCallbacks.current.replaceNavigationEntry(latestCallbacks.current.buildNavigationEntry({ kind: "chat" }, roleId));
    }
    return true;
  }

  async function refreshSession(): Promise<void> {
    if (!activeRoleIdRef.current) return;
    const refreshed = await openRole(activeRoleIdRef.current, null, { recordHistory: false });
    if (refreshed) {
      feedback.success("对话已重新载入");
    }
  }

  return { openRole, refreshSession };
}
