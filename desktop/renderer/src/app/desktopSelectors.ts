import {
  collectChatImageHistory,
  findChatImageHistoryEntry,
  findChatImageHistoryIndex,
  resolveChatImageSelectionKey,
} from "../chat/chatImageHistory";
import { resolveChatHeaderTitle, resolveVisibleChatSessionKey } from "../chat/chatHeaderState";
import { isRoleFormDirty } from "../roles/roleFormState";
import { toFileUrl } from "../shared/format";
import type {
  AppMainView,
  RoleFormState,
  RoleRecord,
  SessionPayload,
} from "../shared/types";

type BuildDesktopViewModelArgs = {
  roles: RoleRecord[];
  activeRoleId: string;
  mainView: AppMainView;
  roleForm: RoleFormState;
  activeIllustration: string;
  activeSession: SessionPayload | null;
  selectedChatImageKey: string;
  health: string;
  sendingSessions: Record<string, string>;
};

/** Builds the derived desktop view model from persisted app state. */
export function buildDesktopViewModel({
  roles,
  activeRoleId,
  mainView,
  roleForm,
  activeIllustration,
  activeSession,
  selectedChatImageKey,
  health,
  sendingSessions,
}: BuildDesktopViewModelArgs) {
  const activeRole = roles.find((role) => role.id === activeRoleId) ?? null;
  const detailRoleId = mainView.kind === "role-detail" ? mainView.roleId : activeRoleId;
  const detailRole = roles.find((role) => role.id === detailRoleId) ?? null;
  const bridgeReady = health === "online";
  const roleFormDirty = isRoleFormDirty(roleForm, detailRole);

  const previewAvatar = roleForm.avatarSource || detailRole?.avatar_abs || null;
  const previewIllustrations = roleForm.illustrationSources.length
    ? roleForm.illustrationSources
    : (detailRole?.illustrations_abs ?? []).filter(
      (path) => !roleForm.removedIllustrations.includes(path),
    );
  const roleChatBackground = detailRole?.chat_background_abs ?? "";
  const visibleIllustration = activeIllustration || roleChatBackground;
  const visibleIllustrationUrl = visibleIllustration ? toFileUrl(visibleIllustration) : "";
  const chatBackgroundUrl = visibleIllustrationUrl;
  const activeSessionKey = activeSession?.key ?? "";
  const visibleChatSessionKey = resolveVisibleChatSessionKey(activeRoleId, activeSessionKey);
  const isVisibleChatSending = Boolean(visibleChatSessionKey && sendingSessions[visibleChatSessionKey]);
  const headerTitle = resolveChatHeaderTitle({
    activeRoleName: activeRole?.name ?? null,
    activeSessionKey: visibleChatSessionKey,
    sendingSessions,
  });
  const chatImageHistory = collectChatImageHistory(activeSession);
  const resolvedSelectedChatImageKey = resolveChatImageSelectionKey(chatImageHistory, selectedChatImageKey);
  const selectedChatImageIndex = findChatImageHistoryIndex(chatImageHistory, resolvedSelectedChatImageKey);
  const selectedChatImageEntry = findChatImageHistoryEntry(chatImageHistory, resolvedSelectedChatImageKey);
  const resolvedChatImagePath = selectedChatImageEntry?.path ?? "";
  const latestChatGeneratedImageKey = chatImageHistory[chatImageHistory.length - 1]?.historyKey ?? "";
  const selectedChatImagePosition = selectedChatImageIndex >= 0 ? selectedChatImageIndex + 1 : 0;

  return {
    activeRole,
    detailRoleId,
    detailRole,
    bridgeReady,
    roleFormDirty,
    previewAvatar,
    previewIllustrations,
    roleChatBackground,
    visibleIllustrationUrl,
    chatBackgroundUrl,
    activeSessionKey,
    visibleChatSessionKey,
    isVisibleChatSending,
    headerTitle,
    chatImageHistory,
    resolvedChatImagePath,
    selectedChatImageIndex,
    selectedChatImageEntry,
    latestChatGeneratedImageKey,
    selectedChatImagePosition,
  };
}
