import { useRef, useState } from "react";
import type React from "react";
import {
  cloneView,
  navigationEntriesEqual,
  type NavigationEntry,
} from "./appState";
import type { RoleRecord, SessionPayload } from "../shared/types";
import type { AppMainView } from "../shared/types";
import type { SettingsSectionId } from "../settings/SettingsSidebar";
import type { SettingsSubsectionMemory } from "../settings/useSettingsSubsectionMemory";

type RoleWorkspaceView = Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>;

type UseNavigationHistoryArgs = {
  mainView: AppMainView;
  settingsSection: SettingsSectionId;
  /**
   * The last active subtab per settings section id (issue #230 AC 4),
   * lifted to the app shell alongside `settingsSection` so it (a) survives
   * a section swap that unmounts the settings page's own internal state,
   * and (b) can be snapshotted into each `NavigationEntry` for back/forward.
   * Owned by `useSettingsSubsectionMemory`, not by this hook: this hook only
   * reads/writes through it (`resolve`/`remember`), it does not know how
   * settings subtabs are resolved — that stays this hook's own domain
   * boundary (navigation, not settings metadata).
   */
  settingsSubsectionMemory: SettingsSubsectionMemory;
  activeRoleIdRef: React.MutableRefObject<string>;
  lastNonSettingsViewRef: React.MutableRefObject<AppMainView>;
  roles: RoleRecord[];
  setSettingsSection: React.Dispatch<React.SetStateAction<SettingsSectionId>>;
  /** Opens the left sidebar for a workspace whose navigation lives there (see `useLeftSidebarState`). */
  revealSidebar: () => void;
  setMainView: React.Dispatch<React.SetStateAction<AppMainView>>;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
};

/** Manages desktop view history and route-style transitions between major surfaces. */
export function useNavigationHistory({
  mainView,
  settingsSection,
  settingsSubsectionMemory,
  activeRoleIdRef,
  lastNonSettingsViewRef,
  roles,
  setSettingsSection,
  revealSidebar,
  setMainView,
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
    subsectionId = settingsSubsectionMemory.resolve(section) ?? "",
  ): NavigationEntry {
    const resolvedRoleId = view.kind === "role-detail" || view.kind === "role-assets" ? view.roleId : roleId;
    return {
      view: cloneView(view),
      activeRoleId: resolvedRoleId,
      settingsSection: section,
      settingsSubsection: subsectionId,
    };
  }

  /**
   * Records a subtab switch within the currently active settings section
   * (issue #230 AC 4): updates the persistent per-section memory, and — if
   * settings is the live view — keeps the top-of-stack history entry's
   * snapshot in sync, so a later back/forward round trip through this exact
   * visit restores the subtab the user actually left on rather than
   * whatever was active when this settings visit was first pushed.
   */
  function updateSettingsSubsection(sectionId: string, subsectionId: string): void {
    settingsSubsectionMemory.remember(sectionId, subsectionId);
    if (mainView.kind === "settings" && settingsSection === sectionId) {
      replaceNavigationEntry(buildNavigationEntry(mainView, activeRoleIdRef.current, sectionId, subsectionId));
    }
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
    setSettingsSection(section);
    revealSidebar();
    setMainView({ kind: "settings" });
  }

  function openRoleWorkspaceView(nextView: RoleWorkspaceView): void {
    revealSidebar();
    setMainView(nextView);
  }

  function openChatView(options?: { recordHistory?: boolean }): void {
    const nextView: AppMainView = { kind: "chat" };
    setMainView(nextView);
    if (options?.recordHistory !== false) {
      pushNavigationEntry(buildNavigationEntry(nextView));
    }
  }

  /** Opens a plugin-contributed nav.page full-page surface by its registry id. */
  function openPluginPage(pageId: string, options?: { recordHistory?: boolean }): void {
    const nextView: AppMainView = { kind: "plugin-page", pageId };
    revealSidebar();
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
    settingsSubsectionMemory.remember(nextEntry.settingsSection, nextEntry.settingsSubsection);
    if (nextEntry.view.kind === "settings") {
      openSettingsView(nextEntry.settingsSection);
      return;
    }
    if (nextEntry.view.kind === "plugin-page") {
      openPluginPage(nextEntry.view.pageId, { recordHistory: false });
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
    openSettingsWorkspace,
    updateSettingsSubsection,
    openRoleWorkspace,
    openPluginPage,
    navigateHistory,
    pushNavigationEntry,
  };
}
