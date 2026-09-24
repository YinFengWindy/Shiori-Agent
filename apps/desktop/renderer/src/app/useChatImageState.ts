import { useEffect, useRef } from "react";
import type { ChatImageHistoryEntry } from "../chat/chatImageHistory";
import type { RoleRecord, SessionPayload } from "../shared/types";
import { applySessionMessageUpdate } from "../chat/applySessionMessageUpdate";
import type { SessionMessageUpdatePayload } from "../shared/types";
import type { FeedbackReporter } from "../shared/feedback/feedbackStore";

type UseChatImageStateArgs = {
  activeRoleId: string;
  activeRole: RoleRecord | null;
  activeSessionKey: string;
  setSelectedChatImageKey: React.Dispatch<React.SetStateAction<string>>;
  chatImageLightboxOpen: boolean;
  setChatImageLightboxOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setAddingChatImageToAssetLibrary: React.Dispatch<React.SetStateAction<boolean>>;
  resolvedChatImagePath: string;
  selectedChatImageIndex: number;
  selectedChatImageEntry: ChatImageHistoryEntry | null;
  chatImageHistory: ChatImageHistoryEntry[];
  latestChatGeneratedImageKey: string;
  openChatLatestImageSidebar: () => void;
  loadRolesFromBridge: () => Promise<unknown>;
  updateCommittedActiveSession: (
    updater: (current: SessionPayload | null) => SessionPayload | null,
  ) => void;
  loadMessagesAround: (messageId: string, sessionKey: string) => Promise<boolean>;
  queueMessageNavigation: (roleId: string, messageKey: string) => void;
  feedback: FeedbackReporter;
};

/** Owns chat image preview, lightbox, and right-rail state for the desktop chat surface. */
export function useChatImageState({
  activeRoleId,
  activeRole,
  activeSessionKey,
  setSelectedChatImageKey,
  chatImageLightboxOpen,
  setChatImageLightboxOpen,
  setAddingChatImageToAssetLibrary,
  resolvedChatImagePath,
  selectedChatImageIndex,
  selectedChatImageEntry,
  chatImageHistory,
  latestChatGeneratedImageKey,
  openChatLatestImageSidebar,
  loadRolesFromBridge,
  updateCommittedActiveSession,
  loadMessagesAround,
  queueMessageNavigation,
  feedback,
}: UseChatImageStateArgs) {
  const latestChatImageRef = useRef<{ sessionKey: string; latestKey: string }>({ sessionKey: "", latestKey: "" });
  function applyPluginImageUpdate(sessionKey: string, update: SessionMessageUpdatePayload): void {
    if (!update.message || update.session.key !== sessionKey) return;
    const message = update.message;
    updateCommittedActiveSession((current) => applySessionMessageUpdate(current, sessionKey, update.session, message));
  }

  function openChatImagePreview(target: { historyKey: string }): void {
    const nextHistoryKey = target.historyKey.trim();
    if (!nextHistoryKey) return;
    setSelectedChatImageKey(nextHistoryKey);
    openChatLatestImageSidebar();
  }

  function openSelectedChatImageLightbox(): void {
    if (!resolvedChatImagePath) return;
    setChatImageLightboxOpen(true);
  }

  function closeSelectedChatImageLightbox(): void {
    setChatImageLightboxOpen(false);
  }

  function locateSelectedChatImageMessage(): void {
    const messageId = selectedChatImageEntry?.messageId ?? "";
    if (!activeRoleId || !activeSessionKey || !messageId) {
      return;
    }
    setChatImageLightboxOpen(false);
    void loadMessagesAround(messageId, activeSessionKey).then((loaded) => {
      if (loaded) {
        queueMessageNavigation(activeRoleId, messageId);
      }
    });
  }

  async function addSelectedChatImageToAssetLibrary(): Promise<void> {
    if (!activeRoleId || !resolvedChatImagePath) return;
    if (activeRole?.illustrations_abs.includes(resolvedChatImagePath)) {
      feedback.info("这张图片已在素材库中");
      return;
    }

    setAddingChatImageToAssetLibrary(true);
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: activeRoleId,
        illustration_sources: [resolvedChatImagePath],
      },
    });
    setAddingChatImageToAssetLibrary(false);
    if (res.error) {
      feedback.error(res.error.message);
      return;
    }
    await loadRolesFromBridge();
    feedback.success("已加入素材库");
  }

  function selectPreviousChatImage(): void {
    if (selectedChatImageIndex <= 0) return;
    const previousHistoryKey = chatImageHistory[selectedChatImageIndex - 1]?.historyKey ?? "";
    if (!previousHistoryKey) return;
    setSelectedChatImageKey(previousHistoryKey);
  }

  function selectNextChatImage(): void {
    if (selectedChatImageIndex < 0 || selectedChatImageIndex >= chatImageHistory.length - 1) return;
    const nextHistoryKey = chatImageHistory[selectedChatImageIndex + 1]?.historyKey ?? "";
    if (!nextHistoryKey) return;
    setSelectedChatImageKey(nextHistoryKey);
  }

  useEffect(() => {
    const sessionKey = activeSessionKey;
    if (!sessionKey) {
      latestChatImageRef.current = { sessionKey: "", latestKey: "" };
      return;
    }

    const previous = latestChatImageRef.current;
    if (previous.sessionKey !== sessionKey) {
      latestChatImageRef.current = { sessionKey, latestKey: latestChatGeneratedImageKey };
      return;
    }

    if (latestChatGeneratedImageKey && latestChatGeneratedImageKey !== previous.latestKey) {
      setSelectedChatImageKey(latestChatGeneratedImageKey);
      openChatLatestImageSidebar();
    }
    latestChatImageRef.current = { sessionKey, latestKey: latestChatGeneratedImageKey };
  }, [activeSessionKey, latestChatGeneratedImageKey, openChatLatestImageSidebar, setSelectedChatImageKey]);

  useEffect(() => {
    if (resolvedChatImagePath) return;
    if (chatImageLightboxOpen) {
      setChatImageLightboxOpen(false);
    }
  }, [chatImageLightboxOpen, resolvedChatImagePath, setChatImageLightboxOpen]);

  return {
    applyPluginImageUpdate,
    openChatImagePreview,
    openSelectedChatImageLightbox,
    closeSelectedChatImageLightbox,
    locateSelectedChatImageMessage,
    addSelectedChatImageToAssetLibrary,
    selectPreviousChatImage,
    selectNextChatImage,
  };
}
