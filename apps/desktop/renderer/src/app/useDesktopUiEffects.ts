import { useEffect } from "react";
import type React from "react";

type UseDesktopUiEffectsArgs = {
  sidebarAnimating: boolean;
  setSidebarAnimating: React.Dispatch<React.SetStateAction<boolean>>;
  pendingMessageNavigation: { roleId: string; messageKey: string } | null;
  setHighlightedMessageKey: React.Dispatch<React.SetStateAction<string>>;
  highlightedMessageKey: string;
  previewIllustrations: string[];
  activeIllustration: string;
  persistedChatBackground: string;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  sidebarAnimationDurationMs: number;
  sidebarAutoCollapseWindowWidth: number;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
};

/** Keeps a message target pending while its destination role session is opening. */
export function shouldWaitForMessageNavigation(
  pendingMessageNavigation: { roleId: string; messageKey: string } | null,
  activeSessionKey: string,
  activeRoleId: string,
  activeSessionMessageKeys: readonly string[],
): boolean {
  return Boolean(
    pendingMessageNavigation
    && (
      !activeSessionKey
      || pendingMessageNavigation.roleId !== activeRoleId
      || !activeSessionMessageKeys.includes(pendingMessageNavigation.messageKey)
    ),
  );
}

/** Runs UI-only desktop effects such as sidebar timers and message highlight retries. */
export function useDesktopUiEffects({
  sidebarAnimating,
  setSidebarAnimating,
  pendingMessageNavigation,
  setHighlightedMessageKey,
  highlightedMessageKey,
  previewIllustrations,
  activeIllustration,
  persistedChatBackground,
  setActiveIllustration,
  sidebarAnimationDurationMs,
  sidebarAutoCollapseWindowWidth,
  setSidebarCollapsed,
}: UseDesktopUiEffectsArgs) {
  useEffect(() => {
    if (!sidebarAnimating) return undefined;
    const timer = window.setTimeout(() => setSidebarAnimating(false), sidebarAnimationDurationMs + 40);
    return () => window.clearTimeout(timer);
  }, [setSidebarAnimating, sidebarAnimating, sidebarAnimationDurationMs]);

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

  useEffect(() => {
    if (!highlightedMessageKey) return;
    if (
      pendingMessageNavigation
      && pendingMessageNavigation.messageKey === highlightedMessageKey
    ) {
      return;
    }
    const timer = window.setTimeout(() => setHighlightedMessageKey(""), 2400);
    return () => window.clearTimeout(timer);
  }, [
    highlightedMessageKey,
    pendingMessageNavigation,
    setHighlightedMessageKey,
  ]);

  useEffect(() => {
    if (previewIllustrations.length === 0) {
      if (activeIllustration) {
        setActiveIllustration("");
      }
      return;
    }
    if (!previewIllustrations.includes(activeIllustration)) {
      if (persistedChatBackground && previewIllustrations.includes(persistedChatBackground)) {
        setActiveIllustration(persistedChatBackground);
        return;
      }
      setActiveIllustration("");
    }
  }, [
    activeIllustration,
    persistedChatBackground,
    previewIllustrations,
    setActiveIllustration,
  ]);
}
