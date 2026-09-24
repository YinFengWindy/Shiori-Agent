import { buildPluginRoleDraftUpdates, notifyPluginRoleSaved, writePluginRoleSettings } from "../plugins/pluginRoleSettings";
import type React from "react";
import { useRolePluginRefresh } from "./useRolePluginRefresh";
import { waitForMinimumRoleCardBusy } from "./appState";
import type { RoleAssetCategory, RoleRecord, RoleFormState, PendingRoleCardAction, SessionPayload } from "../shared/types";
import type { AppMainView } from "../shared/types";
import type { NavigationEntry } from "./appState";
import { writeRoleMoodConfigToRuntimeConfig } from "../roles/roleMoodConfig";
import { buildRoleProactiveConfig } from "../roles/roleFormState";
import { writeRoleVoiceConfigToRuntimeConfig } from "../roles/roleVoiceConfig";
import type { FeedbackReporter } from "../shared/feedback/feedbackStore";

type UseRoleManagementArgs = {
  activeRoleId: string;
  detailRoleId: string;
  detailRole: RoleRecord | null;
  activeIllustration: string;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
  roleFormRef: React.MutableRefObject<RoleFormState>;
  setSavingRole: React.Dispatch<React.SetStateAction<boolean>>;
  setSavingRoleAssets: React.Dispatch<React.SetStateAction<boolean>>;
  setDeletingRole: React.Dispatch<React.SetStateAction<boolean>>;
  setPendingRoleCardAction: React.Dispatch<React.SetStateAction<PendingRoleCardAction>>;
  feedback: FeedbackReporter;
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  updateRoleForm: (next: React.SetStateAction<RoleFormState>) => void;
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
  openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<boolean>;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
  commitActiveSession: (nextSession: null) => void;
  removeCachedRoleSession: (roleId: string) => void;
  rememberIllustration: (roleId: string, illustration: string) => Promise<void>;
  roleAssetSaveRequestIdRef: React.MutableRefObject<number>;
};

/** Owns persisted role editing, deletion, and asset operations. */
export function useRoleManagement({
  activeRoleId,
  detailRoleId,
  detailRole,
  activeIllustration,
  selectedAvatarAsset,
  selectedChatBackground,
  roleFormRef,
  setSavingRole,
  setSavingRoleAssets,
  setDeletingRole,
  setPendingRoleCardAction,
  feedback,
  setRoles,
  setActiveRoleId,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  setActiveIllustration,
  updateRoleForm,
  openRoleWorkspace,
  buildNavigationEntry,
  replaceNavigationEntry,
  loadRolesFromBridge,
  openRole,
  applyRoleSnapshot,
  commitActiveSession,
  removeCachedRoleSession,
  rememberIllustration,
  roleAssetSaveRequestIdRef,
}: UseRoleManagementArgs) {
  const refreshDetailRoleForPlugins = useRolePluginRefresh({ detailRoleId, detailRole, roleFormRef, loadRolesFromBridge, updateRoleForm, reportError: feedback.error });
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

  async function saveRole(): Promise<void> {
    if (!detailRoleId) return;
    setSavingRole(true);
    const nextRoleForm = roleFormRef.current;
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        name: nextRoleForm.name,
        description: nextRoleForm.description,
        system_prompt: nextRoleForm.systemPrompt,
        profile: nextRoleForm.profile,
        runtime_config: writeRoleVoiceConfigToRuntimeConfig(
          writeRoleMoodConfigToRuntimeConfig(
            {
              ...writePluginRoleSettings(detailRole?.runtime_config ?? {}, nextRoleForm.pluginSettings),
              nsfw_memory_enabled: nextRoleForm.nsfwMemoryEnabled,
            },
            nextRoleForm,
          ),
          nextRoleForm,
        ),
        channel_bindings: nextRoleForm.channelBindings ?? [],
        proactive: buildRoleProactiveConfig(detailRole, nextRoleForm),
        plugin_drafts: buildPluginRoleDraftUpdates(nextRoleForm.pluginSettings, detailRole?.plugin_state),
        avatar_source: nextRoleForm.avatarSource || undefined,
        illustration_sources: nextRoleForm.illustrationSources,
        removed_illustrations: nextRoleForm.removedIllustrations,
      },
    });
    if (res.error) {
      setSavingRole(false);
      feedback.error(`角色保存失败：${res.error.message}`);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    await notifyPluginRoleSaved(nextRoleForm.pluginSettings, detailRole?.runtime_config, detailRole?.plugin_state);
    const { resolvedRole } = await refreshRolesAndResolveRole(updated);
    updateRoleForm((current) => ({
      ...current,
      avatarSource: "",
      illustrationSources: [],
      removedIllustrations: [],
      pendingVoiceAssetDeletes: [],
    }));
    await openRole(updated.id, resolvedRole, { recordHistory: false });
    setSavingRole(false);
    feedback.success("角色已保存");
  }

  async function saveRoleAssets(nextSelection?: {
    avatarAsset?: string;
    chatBackground?: string;
    moodIllustrationBindings?: Record<string, string>;
  }): Promise<void> {
    if (!detailRoleId) return;
    const requestId = roleAssetSaveRequestIdRef.current + 1;
    roleAssetSaveRequestIdRef.current = requestId;
    setSavingRoleAssets(true);
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
              ...writePluginRoleSettings(detailRole?.runtime_config ?? {}, roleFormRef.current.pluginSettings),
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
    if (roleAssetSaveRequestIdRef.current === requestId) {
      setSavingRoleAssets(false);
    }
    if (roleAssetSaveRequestIdRef.current !== requestId) {
      return;
    }
    if (res.error) {
      feedback.error(res.error.message);
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
    feedback.success("角色素材已更新");
    updateRoleForm({ ...pendingRoleForm });
    openRoleWorkspace({ kind: "role-assets", roleId: resolvedRole.id }, { recordHistory: false });
  }

  async function deleteRole(roleIdOverride?: string): Promise<void> {
    const roleId = roleIdOverride || activeRoleId;
    if (!roleId) return;
    const startedAt = Date.now();
    setDeletingRole(true);
    setPendingRoleCardAction({ roleId, action: "delete" });
    const res = await window.miraDesktop.invoke({
      method: "roles.delete",
      payload: { role_id: roleId },
    });
    await waitForMinimumRoleCardBusy(startedAt);
    setDeletingRole(false);
    if (res.error) {
      setPendingRoleCardAction(null);
      feedback.error(res.error.message);
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
    feedback.success("角色已删除");
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

  async function pickRoleAssets(categoryId: string): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: true });
    if (!files.length || !detailRoleId) return;
    setSavingRoleAssets(true);
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        illustration_sources: files,
        illustration_category_id: categoryId,
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      feedback.error(res.error.message);
      return;
    }
    const updated = res.payload.role as RoleRecord;
    const { resolvedRole } = await refreshRolesAndResolveRole(updated);
    syncRoleAssetSelections(resolvedRole);
    openRoleWorkspace({ kind: "role-assets", roleId: resolvedRole.id }, { recordHistory: false });
  }

  async function updateRoleAssetOrganization(
    assetCategories: RoleAssetCategory[],
    assetCategoryBindings: Record<string, string>,
    removedIllustrations: string[] = [],
  ): Promise<boolean> {
    if (!detailRoleId) return false;
    setSavingRoleAssets(true);
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        asset_categories: assetCategories,
        asset_category_bindings: assetCategoryBindings,
        removed_illustrations: removedIllustrations,
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      feedback.error(res.error.message);
      return false;
    }
    const updated = res.payload.role as RoleRecord;
    setRoles((current) => current.map((role) => role.id === updated.id ? updated : role));
    applyRoleSnapshot(updated);
    syncRoleAssetSelections(updated);
    feedback.success("素材分类已更新");
    openRoleWorkspace({ kind: "role-assets", roleId: updated.id }, { recordHistory: false });
    return true;
  }

  async function removeRoleAsset(relPath: string): Promise<void> {
    const cleanPath = relPath.trim();
    if (!cleanPath || !detailRoleId || !detailRole) return;
    const removedIndex = detailRole.illustrations.findIndex((item) => item === cleanPath);
    const removedAbsPath = removedIndex >= 0 ? (detailRole.illustrations_abs[removedIndex] ?? "") : "";
    setSavingRoleAssets(true);
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: detailRoleId,
        removed_illustrations: [cleanPath],
      },
    });
    setSavingRoleAssets(false);
    if (res.error) {
      feedback.error(res.error.message);
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
    feedback.success("素材已删除");
    openRoleWorkspace({ kind: "role-assets", roleId: resolvedRole.id }, { recordHistory: false });
  }

  return {
    saveRole,
    saveRoleAssets,
    confirmDeleteRole,
    pickRoleAssets,
    removeRoleAsset,
    updateRoleAssetOrganization,
    refreshDetailRoleForPlugins,
  };
}
