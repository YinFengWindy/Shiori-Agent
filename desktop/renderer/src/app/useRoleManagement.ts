import type React from "react";
import { createEmptyNewRoleForm, createPendingRoleRecord, minRoleCardBusyMs } from "./appState";
import type { RoleRecord, RoleFormState, NewRoleFormState, PendingRoleCardAction, SessionPayload } from "../shared/types";
import type { AppMainView } from "../shared/types";
import type { NavigationEntry } from "./appState";
import { writeRoleMoodConfigToRuntimeConfig } from "../roles/roleMoodConfig";

type UseRoleManagementArgs = {
  activeRoleId: string;
  detailRoleId: string;
  detailRole: RoleRecord | null;
  activeIllustration: string;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
  roleFormRef: React.MutableRefObject<RoleFormState>;
  newRoleFormRef: React.MutableRefObject<NewRoleFormState>;
  activeRoleIdRef: React.MutableRefObject<string>;
  setCreating: React.Dispatch<React.SetStateAction<boolean>>;
  setSavingRole: React.Dispatch<React.SetStateAction<boolean>>;
  setSavingRoleAssets: React.Dispatch<React.SetStateAction<boolean>>;
  setDeletingRole: React.Dispatch<React.SetStateAction<boolean>>;
  setPendingRoleCardAction: React.Dispatch<React.SetStateAction<PendingRoleCardAction>>;
  setWorkspaceFeedback: React.Dispatch<React.SetStateAction<{ tone: "success" | "error"; message: string } | null>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  updateRoleForm: (next: React.SetStateAction<RoleFormState>) => void;
  updateNewRoleForm: (next: React.SetStateAction<NewRoleFormState>) => void;
  openRoleWorkspace: (
    nextView: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>,
    options?: { recordHistory?: boolean },
  ) => void;
  buildNavigationEntry: (
    view: AppMainView,
    roleId?: string,
  ) => NavigationEntry;
  replaceNavigationEntry: (entry: NavigationEntry) => void;
  loadRolesFromBridge: () => Promise<RoleRecord[] | null>;
  openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<void>;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
  commitActiveSession: (nextSession: null) => void;
  removeCachedRoleSession: (roleId: string) => void;
  rememberIllustration: (roleId: string, illustration: string) => Promise<void>;
};

async function waitForMinimumRoleCardBusy(startedAt: number): Promise<void> {
  const elapsed = Date.now() - startedAt;
  if (elapsed >= minRoleCardBusyMs) {
    return;
  }
  await new Promise((resolve) => window.setTimeout(resolve, minRoleCardBusyMs - elapsed));
}

/** Owns role CRUD and role asset operations so the root app only composes them. */
export function useRoleManagement({
  activeRoleId,
  detailRoleId,
  detailRole,
  activeIllustration,
  selectedAvatarAsset,
  selectedChatBackground,
  roleFormRef,
  newRoleFormRef,
  activeRoleIdRef,
  setCreating,
  setSavingRole,
  setSavingRoleAssets,
  setDeletingRole,
  setPendingRoleCardAction,
  setWorkspaceFeedback,
  setError,
  setNotice,
  setRoles,
  setActiveRoleId,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  setActiveIllustration,
  updateRoleForm,
  updateNewRoleForm,
  openRoleWorkspace,
  buildNavigationEntry,
  replaceNavigationEntry,
  loadRolesFromBridge,
  openRole,
  applyRoleSnapshot,
  commitActiveSession,
  removeCachedRoleSession,
  rememberIllustration,
}: UseRoleManagementArgs) {
  async function refreshRolesAndResolveRole(updated: RoleRecord): Promise<{
    resolvedRole: RoleRecord;
    nextRoles: RoleRecord[] | null;
  }> {
    const nextRoles = await loadRolesFromBridge();
    return {
      resolvedRole: nextRoles?.find((item) => item.id === updated.id) ?? updated,
      nextRoles,
    };
  }

  function syncRoleAssetSelections(updated: RoleRecord): void {
    setSelectedAvatarAsset(updated.avatar ?? "");
    setSelectedChatBackground(updated.chat_background ?? "");
  }

  function navigateToRolesList(roleId: string): void {
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, roleId));
  }

  async function createRole(): Promise<void> {
    const name = newRoleFormRef.current.name.trim();
    const systemPrompt = newRoleFormRef.current.systemPrompt.trim();
    if (!name || !systemPrompt) {
      const message = "角色名称和系统提示词不能为空。";
      setError(message);
      setWorkspaceFeedback({ tone: "error", message: `角色创建失败：${message}` });
      return;
    }
    const pendingRoleId = `pending-create:${Date.now()}`;
    const pendingRole = createPendingRoleRecord(pendingRoleId, newRoleFormRef.current);
    const previousActiveRoleId = activeRoleIdRef.current;
    const startedAt = Date.now();
    setCreating(true);
    setError("");
    setWorkspaceFeedback(null);
    setPendingRoleCardAction({ roleId: pendingRoleId, action: "create" });
    setRoles((current) => [pendingRole, ...current]);
    applyRoleSnapshot(pendingRole);
    openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, pendingRoleId));
    const res = await window.miraDesktop.invoke({
      method: "roles.create",
      payload: {
        name,
        description: newRoleFormRef.current.description,
        system_prompt: systemPrompt,
      },
    });
    await waitForMinimumRoleCardBusy(startedAt);
    setCreating(false);
    if (res.error) {
      setPendingRoleCardAction(null);
      setRoles((current) => current.filter((item) => item.id !== pendingRoleId));
      setActiveRoleId(previousActiveRoleId);
      activeRoleIdRef.current = previousActiveRoleId;
      openRoleWorkspace({ kind: "role-create" }, { recordHistory: false });
      replaceNavigationEntry(buildNavigationEntry({ kind: "role-create" }, previousActiveRoleId));
      setError(res.error.message);
      setWorkspaceFeedback({ tone: "error", message: `角色创建失败：${res.error.message}` });
      return;
    }
    const role = res.payload.role as RoleRecord;
    activeRoleIdRef.current = role.id;
    setActiveRoleId(role.id);
    setPendingRoleCardAction({ roleId: role.id, action: "create" });
    setRoles((current) => {
      const withoutPending = current.filter((item) => item.id !== pendingRoleId);
      const existing = withoutPending.find((item) => item.id === role.id);
      if (existing) {
        return [role, ...withoutPending.filter((item) => item.id !== role.id)];
      }
      return [role, ...withoutPending];
    });
    applyRoleSnapshot(role);
    const { resolvedRole, nextRoles } = await refreshRolesAndResolveRole(role);
    if (!nextRoles?.some((item) => item.id === role.id)) {
      setRoles((current) => {
        const existing = current.find((item) => item.id === role.id);
        if (existing) {
          return [resolvedRole, ...current.filter((item) => item.id !== role.id)];
        }
        return [resolvedRole, ...current];
      });
    }
    await openRole(role.id, resolvedRole, { recordHistory: false });
    navigateToRolesList(resolvedRole.id);
    setPendingRoleCardAction(null);
    updateNewRoleForm(createEmptyNewRoleForm());
    setWorkspaceFeedback({ tone: "success", message: "角色创建成功。" });
  }

  async function saveRole(): Promise<void> {
    if (!activeRoleId) return;
    setSavingRole(true);
    setError("");
    setWorkspaceFeedback(null);
    const nextRoleForm = roleFormRef.current;
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: activeRoleId,
        name: nextRoleForm.name,
        description: nextRoleForm.description,
        system_prompt: nextRoleForm.systemPrompt,
        runtime_config: writeRoleMoodConfigToRuntimeConfig(
          {
            ...(detailRole?.runtime_config ?? {}),
            nsfw_memory_enabled: nextRoleForm.nsfwMemoryEnabled,
          },
          nextRoleForm,
        ),
        avatar_source: nextRoleForm.avatarSource || undefined,
        illustration_sources: nextRoleForm.illustrationSources,
        removed_illustrations: nextRoleForm.removedIllustrations,
      },
    });
    setSavingRole(false);
    if (res.error) {
      setError(res.error.message);
      setWorkspaceFeedback({ tone: "error", message: `角色保存失败：${res.error.message}` });
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const { resolvedRole } = await refreshRolesAndResolveRole(updated);
    updateRoleForm((current) => ({ ...current, avatarSource: "", illustrationSources: [], removedIllustrations: [] }));
    await openRole(updated.id, resolvedRole, { recordHistory: false });
    navigateToRolesList(updated.id);
    setWorkspaceFeedback({ tone: "success", message: "角色保存成功。" });
  }

  async function saveRoleAssets(nextSelection?: {
    avatarAsset?: string;
    chatBackground?: string;
    moodIllustrationBindings?: Record<string, string>;
  }): Promise<void> {
    if (!detailRoleId) return;
    setSavingRoleAssets(true);
    setError("");
    const pendingRoleForm = roleFormRef.current;
    const hasAvatarSelection = Boolean(
      nextSelection && Object.prototype.hasOwnProperty.call(nextSelection, "avatarAsset"),
    );
    const hasChatBackgroundSelection = Boolean(
      nextSelection && Object.prototype.hasOwnProperty.call(nextSelection, "chatBackground"),
    );
    const avatarAsset = hasAvatarSelection
      ? (nextSelection?.avatarAsset ?? "")
      : selectedAvatarAsset;
    const chatBackground = hasChatBackgroundSelection
      ? (nextSelection?.chatBackground ?? "")
      : selectedChatBackground;
    const nextMoodIllustrationBindings = nextSelection?.moodIllustrationBindings;
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        avatar_asset: avatarAsset || undefined,
        chat_background: chatBackground || undefined,
        clear_avatar: hasAvatarSelection && !avatarAsset,
        clear_chat_background: hasChatBackgroundSelection && !chatBackground,
        runtime_config: nextMoodIllustrationBindings
          ? writeRoleMoodConfigToRuntimeConfig(
            {
              ...(detailRole?.runtime_config ?? {}),
              nsfw_memory_enabled: roleFormRef.current.nsfwMemoryEnabled,
            },
            {
              ...roleFormRef.current,
              moodIllustrationBindings: nextMoodIllustrationBindings,
            },
          )
          : undefined,
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const { resolvedRole } = await refreshRolesAndResolveRole(updated);
    syncRoleAssetSelections(resolvedRole);
    if (hasChatBackgroundSelection) {
      const nextIllustration = resolvedRole.chat_background_abs ?? "";
      setActiveIllustration(nextIllustration);
      await rememberIllustration(resolvedRole.id, nextIllustration);
    }
    setNotice("角色素材已更新。");
    updateRoleForm({ ...pendingRoleForm });
    openRoleWorkspace({ kind: "role-assets", roleId: resolvedRole.id }, { recordHistory: false });
  }

  async function deleteRole(roleIdOverride?: string): Promise<void> {
    const roleId = roleIdOverride || activeRoleId;
    if (!roleId) return;
    const startedAt = Date.now();
    setDeletingRole(true);
    setPendingRoleCardAction({ roleId, action: "delete" });
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.delete",
      payload: { role_id: roleId },
    });
    await waitForMinimumRoleCardBusy(startedAt);
    setDeletingRole(false);
    if (res.error) {
      setPendingRoleCardAction(null);
      setError(res.error.message);
      return;
    }
    const nextRoles = (await loadRolesFromBridge()) ?? [];
    setPendingRoleCardAction(null);
    if (!roleIdOverride || roleId === activeRoleId) {
      setActiveRoleId("");
      commitActiveSession(null);
      setActiveIllustration("");
    }
    removeCachedRoleSession(roleId);
    setNotice("角色已删除。");
    if (nextRoles[0]) {
      await openRole(nextRoles[0].id, nextRoles[0], { recordHistory: false });
      navigateToRolesList(nextRoles[0].id);
      return;
    }
    navigateToRolesList("");
  }

  async function confirmDeleteRole(pendingDeleteRoleId: string, clearPendingDeleteRoleId: () => void): Promise<void> {
    if (!pendingDeleteRoleId) return;
    const targetRoleId = pendingDeleteRoleId;
    clearPendingDeleteRoleId();
    await deleteRole(targetRoleId);
  }

  async function pickRoleAssets(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: true });
    if (!files.length || !detailRoleId) return;
    setSavingRoleAssets(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        illustration_sources: files,
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const { resolvedRole } = await refreshRolesAndResolveRole(updated);
    syncRoleAssetSelections(resolvedRole);
    openRoleWorkspace({ kind: "role-assets", roleId: resolvedRole.id }, { recordHistory: false });
  }

  async function removeRoleAsset(relPath: string): Promise<void> {
    const cleanPath = relPath.trim();
    if (!cleanPath || !detailRoleId || !detailRole) return;
    const removedIndex = detailRole.illustrations.findIndex((item) => item === cleanPath);
    const removedAbsPath = removedIndex >= 0 ? (detailRole.illustrations_abs[removedIndex] ?? "") : "";
    setSavingRoleAssets(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        removed_illustrations: [cleanPath],
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const { resolvedRole } = await refreshRolesAndResolveRole(updated);
    syncRoleAssetSelections(resolvedRole);
    if (!removedAbsPath || activeIllustration === removedAbsPath) {
      const nextIllustration = resolvedRole.chat_background_abs ?? "";
      setActiveIllustration(nextIllustration);
      await rememberIllustration(resolvedRole.id, nextIllustration);
    }
    setNotice("角色素材已删除。");
    openRoleWorkspace({ kind: "role-assets", roleId: resolvedRole.id }, { recordHistory: false });
  }

  return {
    createRole,
    saveRole,
    saveRoleAssets,
    confirmDeleteRole,
    pickRoleAssets,
    removeRoleAsset,
  };
}
