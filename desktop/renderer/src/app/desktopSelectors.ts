import {
  collectChatImageHistory,
  findChatImageHistoryEntry,
  findChatImageHistoryIndex,
  resolveChatImageSelection,
} from "../chat/chatImageHistory";
import { resolveChatHeaderTitle, resolveVisibleChatSessionKey } from "../chat/chatHeaderState";
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
  selectedChatImagePath: string;
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
  selectedChatImagePath,
  health,
  sendingSessions,
}: BuildDesktopViewModelArgs) {
  const activeRole = roles.find((role) => role.id === activeRoleId) ?? null;
  const detailRoleId = mainView.kind === "role-detail" ? mainView.roleId : activeRoleId;
  const detailRole = roles.find((role) => role.id === detailRoleId) ?? null;
  const bridgeReady = health === "online";
  const roleFormDirty = Boolean(
    detailRole
      && (
        roleForm.name !== detailRole.name
        || roleForm.description !== detailRole.description
        || roleForm.systemPrompt !== detailRole.system_prompt
        || roleForm.nsfwMemoryEnabled !== Boolean(detailRole.runtime_config?.nsfw_memory_enabled)
        || Boolean(roleForm.avatarSource)
        || roleForm.illustrationSources.length > 0
        || roleForm.removedIllustrations.length > 0
      )
  );

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
  const resolvedChatImagePath = resolveChatImageSelection(chatImageHistory, selectedChatImagePath);
  const selectedChatImageIndex = findChatImageHistoryIndex(chatImageHistory, resolvedChatImagePath);
  const selectedChatImageEntry = findChatImageHistoryEntry(chatImageHistory, resolvedChatImagePath);
  const latestChatGeneratedImagePath = chatImageHistory[chatImageHistory.length - 1]?.path ?? "";
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
    latestChatGeneratedImagePath,
    selectedChatImagePosition,
  };
}
