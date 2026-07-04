import { useEffect, useRef } from "react";
import type { RoleRecord } from "../shared/types";

type ChatImageHistoryEntry = {
  path: string;
  messageId?: string | null;
};

type UseChatImageStateArgs = {
  activeRoleId: string;
  activeRole: RoleRecord | null;
  activeSessionKey: string;
  selectedChatImagePath: string;
  setSelectedChatImagePath: React.Dispatch<React.SetStateAction<string>>;
  chatImageLightboxOpen: boolean;
  setChatImageLightboxOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setAddingChatImageToAssetLibrary: React.Dispatch<React.SetStateAction<boolean>>;
  resolvedChatImagePath: string;
  selectedChatImageIndex: number;
  selectedChatImageEntry: ChatImageHistoryEntry | null;
  chatImageHistory: ChatImageHistoryEntry[];
  latestChatGeneratedImagePath: string;
  sidebarAutoCollapseWindowWidth: number;
  openChatLatestImageSidebar: () => void;
  loadRolesFromBridge: () => Promise<unknown>;
  queueMessageNavigation: (roleId: string, messageKey: string) => void;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setSidebarAnimating: React.Dispatch<React.SetStateAction<boolean>>;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
};

/** Owns chat image preview, lightbox, and right-rail state for the desktop chat surface. */
export function useChatImageState({
  activeRoleId,
  activeRole,
  activeSessionKey,
  selectedChatImagePath,
  setSelectedChatImagePath,
  chatImageLightboxOpen,
  setChatImageLightboxOpen,
  setAddingChatImageToAssetLibrary,
  resolvedChatImagePath,
  selectedChatImageIndex,
  selectedChatImageEntry,
  chatImageHistory,
  latestChatGeneratedImagePath,
  sidebarAutoCollapseWindowWidth,
  openChatLatestImageSidebar,
  loadRolesFromBridge,
  queueMessageNavigation,
  setError,
  setNotice,
  setSidebarAnimating,
  setSidebarCollapsed,
}: UseChatImageStateArgs) {
  const latestChatImageRef = useRef<{ sessionKey: string; latestPath: string }>({ sessionKey: "", latestPath: "" });

  function openChatImagePreview(path: string): void {
    const cleanPath = path.trim();
    if (!cleanPath) return;
    setSelectedChatImagePath(cleanPath);
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
    if (!activeRoleId || !selectedChatImageEntry?.messageId) {
      return;
    }
    setChatImageLightboxOpen(false);
    queueMessageNavigation(activeRoleId, selectedChatImageEntry.messageId);
  }

  async function addSelectedChatImageToAssetLibrary(): Promise<void> {
    if (!activeRoleId || !resolvedChatImagePath) return;
    if (activeRole?.illustrations_abs.includes(resolvedChatImagePath)) {
      setNotice("当前图片已在素材库中。");
      return;
    }

    setAddingChatImageToAssetLibrary(true);
    setError("");
    const res = await window.miraDesktop.invoke({
      method: "roles.update",
      payload: {
        role_id: activeRoleId,
        illustration_sources: [resolvedChatImagePath],
      },
    });
    setAddingChatImageToAssetLibrary(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    await loadRolesFromBridge();
    setNotice("已加入素材库。");
  }

  function selectPreviousChatImage(): void {
    if (selectedChatImageIndex <= 0) return;
    const previousPath = chatImageHistory[selectedChatImageIndex - 1]?.path ?? "";
    if (!previousPath) return;
    setSelectedChatImagePath(previousPath);
  }

  function selectNextChatImage(): void {
    if (selectedChatImageIndex < 0 || selectedChatImageIndex >= chatImageHistory.length - 1) return;
    const nextPath = chatImageHistory[selectedChatImageIndex + 1]?.path ?? "";
    if (!nextPath) return;
    setSelectedChatImagePath(nextPath);
  }

  useEffect(() => {
    const sessionKey = activeSessionKey;
    if (!sessionKey) {
      latestChatImageRef.current = { sessionKey: "", latestPath: "" };
      return;
    }

    const previous = latestChatImageRef.current;
    if (previous.sessionKey !== sessionKey) {
      latestChatImageRef.current = { sessionKey, latestPath: latestChatGeneratedImagePath };
      return;
    }

    if (latestChatGeneratedImagePath && latestChatGeneratedImagePath !== previous.latestPath) {
      setSelectedChatImagePath(latestChatGeneratedImagePath);
      openChatLatestImageSidebar();
    }
    latestChatImageRef.current = { sessionKey, latestPath: latestChatGeneratedImagePath };
  }, [activeSessionKey, latestChatGeneratedImagePath, openChatLatestImageSidebar]);

  useEffect(() => {
    if (resolvedChatImagePath) return;
    if (chatImageLightboxOpen) {
      setChatImageLightboxOpen(false);
    }
  }, [chatImageLightboxOpen, resolvedChatImagePath]);

  useEffect(() => {
    function collapseSidebarForNarrowWindow(): void {
      if (window.innerWidth < sidebarAutoCollapseWindowWidth) {
        setSidebarAnimating(true);
        setSidebarCollapsed(true);
      }
    }

    collapseSidebarForNarrowWindow();
    window.addEventListener("resize", collapseSidebarForNarrowWindow);
    return () => window.removeEventListener("resize", collapseSidebarForNarrowWindow);
  }, [setSidebarAnimating, setSidebarCollapsed, sidebarAutoCollapseWindowWidth]);

  return {
    openChatImagePreview,
    openSelectedChatImageLightbox,
    closeSelectedChatImageLightbox,
    locateSelectedChatImageMessage,
    addSelectedChatImageToAssetLibrary,
    selectPreviousChatImage,
    selectNextChatImage,
  };
}
