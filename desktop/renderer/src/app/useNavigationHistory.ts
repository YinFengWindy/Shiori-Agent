import { useRef, useState } from "react";
import type React from "react";
import {
  cloneView,
  navigationEntriesEqual,
  sidebarMaxWidth,
  sidebarMinWidth,
  type NavigationEntry,
} from "./appState";
import type { RoleRecord, SessionPayload } from "../shared/types";
import type { AppMainView } from "../shared/types";
import type { SettingsSectionId } from "../settings/SettingsSidebar";

type RoleWorkspaceView = Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>;

type UseNavigationHistoryArgs = {
  mainView: AppMainView;
  settingsSection: SettingsSectionId;
  activeRoleIdRef: React.MutableRefObject<string>;
  lastNonSettingsViewRef: React.MutableRefObject<AppMainView>;
  roles: RoleRecord[];
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setSettingsSearch: React.Dispatch<React.SetStateAction<string>>;
  setSettingsSection: React.Dispatch<React.SetStateAction<SettingsSectionId>>;
  setSidebarAnimating: React.Dispatch<React.SetStateAction<boolean>>;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  setSidebarWidth: React.Dispatch<React.SetStateAction<number>>;
  setMainView: React.Dispatch<React.SetStateAction<AppMainView>>;
  imageHistorySidebarOpen: () => void;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
};

/** Manages desktop view history and route-style transitions between major surfaces. */
export function useNavigationHistory({
  mainView,
  settingsSection,
  activeRoleIdRef,
  lastNonSettingsViewRef,
  roles,
  setError,
  setNotice,
  setSettingsSearch,
  setSettingsSection,
  setSidebarAnimating,
  setSidebarCollapsed,
  setSidebarWidth,
  setMainView,
  imageHistorySidebarOpen,
  applyRoleSnapshot,
}: UseNavigationHistoryArgs) {
  const navigationHistoryRef = useRef<NavigationEntry[]>([]);
  const navigationHistoryIndexRef = useRef(-1);
  const [canGoBack, setCanGoBack] = useState(false);
  const [canGoForward, setCanGoForward] = useState(false);

  function buildNavigationEntry(
    view: AppMainView,
    roleId = activeRoleIdRef.current,
    section = settingsSection,
  ): NavigationEntry {
    const resolvedRoleId = view.kind === "role-detail" || view.kind === "role-assets" ? view.roleId : roleId;
    return {
      view: cloneView(view),
      activeRoleId: resolvedRoleId,
      settingsSection: section,
    };
  }

  function syncNavigationState(): void {
    setCanGoBack(navigationHistoryIndexRef.current > 0);
    setCanGoForward(
      navigationHistoryIndexRef.current >= 0
      && navigationHistoryIndexRef.current < navigationHistoryRef.current.length - 1,
    );
  }

  function pushNavigationEntry(entry: NavigationEntry): void {
    const nextHistory = navigationHistoryRef.current.slice(0, navigationHistoryIndexRef.current + 1);
    const previous = nextHistory[nextHistory.length - 1];
    if (previous && navigationEntriesEqual(previous, entry)) {
      navigationHistoryRef.current = nextHistory;
      navigationHistoryIndexRef.current = nextHistory.length - 1;
      syncNavigationState();
      return;
    }
    nextHistory.push(entry);
    navigationHistoryRef.current = nextHistory;
    navigationHistoryIndexRef.current = nextHistory.length - 1;
    syncNavigationState();
  }

  function replaceNavigationEntry(entry: NavigationEntry): void {
    if (navigationHistoryIndexRef.current < 0) {
      navigationHistoryRef.current = [entry];
      navigationHistoryIndexRef.current = 0;
      syncNavigationState();
      return;
    }
    const nextHistory = [...navigationHistoryRef.current];
    nextHistory[navigationHistoryIndexRef.current] = entry;
    navigationHistoryRef.current = nextHistory;
    syncNavigationState();
  }

  function openSettingsView(section: SettingsSectionId = "models"): void {
    lastNonSettingsViewRef.current = mainView;
    setSettingsSearch("");
    setSettingsSection(section);
    setSidebarAnimating(true);
    setSidebarCollapsed(false);
    setSidebarWidth((current) => Math.min(sidebarMaxWidth, Math.max(sidebarMinWidth, current)));
    setMainView({ kind: "settings" });
  }

  function openRoleWorkspaceView(nextView: RoleWorkspaceView): void {
    setSidebarAnimating(true);
    setSidebarCollapsed(false);
    setMainView(nextView);
  }

  function openChatView(options?: { recordHistory?: boolean }): void {
    const nextView: AppMainView = { kind: "chat" };
    setMainView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  function openImageStudio(options?: { recordHistory?: boolean }): void {
    if (!roles.length) {
      setError("请先创建至少一个角色，再进入生图。");
      setNotice("");
      return;
    }
    const nextView: AppMainView = { kind: "image-studio" };
    setSidebarAnimating(true);
    setSidebarCollapsed(false);
    imageHistorySidebarOpen();
    setMainView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  function openPromptTagLibrary(options?: { recordHistory?: boolean }): void {
    const nextView: AppMainView = { kind: "image-prompt-tags" };
    setSidebarCollapsed(true);
    setMainView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  function openSettingsWorkspace(
    section: SettingsSectionId = "models",
    options?: { recordHistory?: boolean },
  ): void {
    openSettingsView(section);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry({ kind: "settings" }, activeRoleIdRef.current, section));
    }
  }

  function openRoleWorkspace(
    nextView: RoleWorkspaceView,
    options?: { recordHistory?: boolean },
  ): void {
    openRoleWorkspaceView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  async function navigateHistory(
    direction: "back" | "forward",
    openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<boolean>,
  ): Promise<void> {
    const delta = direction === "back" ? -1 : 1;
    const nextIndex = navigationHistoryIndexRef.current + delta;
    const nextEntry = navigationHistoryRef.current[nextIndex];
    if (!nextEntry) return;
    navigationHistoryIndexRef.current = nextIndex;
    syncNavigationState();

    setSettingsSection(nextEntry.settingsSection);
    if (nextEntry.view.kind === "settings") {
      openSettingsView(nextEntry.settingsSection);
      return;
    }
    if (nextEntry.view.kind === "image-studio") {
      openImageStudio({ recordHistory: false });
      return;
    }
    if (nextEntry.view.kind === "image-prompt-tags") {
      openPromptTagLibrary({ recordHistory: false });
      return;
    }
    if (nextEntry.view.kind === "roles-list" || nextEntry.view.kind === "role-create") {
      openRoleWorkspaceView(nextEntry.view);
      return;
    }
    if (nextEntry.view.kind === "role-assets") {
      const assetsView = nextEntry.view;
      const assetsRole = roles.find((role) => role.id === assetsView.roleId) ?? null;
      if (!assetsRole) {
        openRoleWorkspaceView({ kind: "roles-list" });
        return;
      }
      applyRoleSnapshot(assetsRole);
      openRoleWorkspaceView(assetsView);
      void openRole(assetsView.roleId, assetsRole, { recordHistory: false });
      return;
    }
    if (nextEntry.view.kind === "role-detail") {
      const detailView = nextEntry.view;
      const detailRole = roles.find((role) => role.id === detailView.roleId) ?? null;
      if (!detailRole) {
        openRoleWorkspaceView({ kind: "roles-list" });
        return;
      }
      applyRoleSnapshot(detailRole);
      openRoleWorkspaceView(detailView);
      void openRole(detailView.roleId, detailRole, { recordHistory: false });
      return;
    }
    if (nextEntry.activeRoleId) {
      const nextRole = roles.find((role) => role.id === nextEntry.activeRoleId) ?? null;
      if (nextRole) {
        await openRole(nextRole.id, nextRole, { recordHistory: false });
      }
    }
    setMainView({ kind: "chat" });
  }

  return {
    canGoBack,
    canGoForward,
    buildNavigationEntry,
    replaceNavigationEntry,
    openChatView,
    openImageStudio,
    openPromptTagLibrary,
    openSettingsWorkspace,
    openRoleWorkspace,
    navigateHistory,
    pushNavigationEntry,
  };
}
