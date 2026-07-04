import { useEffect } from "react";
import type React from "react";
import type { WorkspaceFeedback } from "./appState";

type UseDesktopUiEffectsArgs = {
  sidebarAnimating: boolean;
  setSidebarAnimating: React.Dispatch<React.SetStateAction<boolean>>;
  activeSessionKey: string;
  pendingMessageNavigation: { roleId: string; messageKey: string } | null;
  activeRoleId: string;
  setHighlightedMessageKey: React.Dispatch<React.SetStateAction<string>>;
  setPendingMessageNavigation: React.Dispatch<React.SetStateAction<{ roleId: string; messageKey: string } | null>>;
  notice: string;
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  workspaceFeedback: WorkspaceFeedback | null;
  setWorkspaceFeedback: React.Dispatch<React.SetStateAction<WorkspaceFeedback | null>>;
  highlightedMessageKey: string;
  previewIllustrations: string[];
  activeIllustration: string;
  persistedChatBackground: string;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  sidebarAnimationDurationMs: number;
  sidebarAutoCollapseWindowWidth: number;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
};

/** Runs UI-only desktop effects such as dismiss timers and message highlight retries. */
export function useDesktopUiEffects({
  sidebarAnimating,
  setSidebarAnimating,
  activeSessionKey,
  pendingMessageNavigation,
  activeRoleId,
  setHighlightedMessageKey,
  setPendingMessageNavigation,
  notice,
  setNotice,
  workspaceFeedback,
  setWorkspaceFeedback,
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
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [notice, setNotice]);

  useEffect(() => {
    if (!workspaceFeedback) return;
    const timer = window.setTimeout(() => setWorkspaceFeedback(null), 2200);
    return () => window.clearTimeout(timer);
  }, [setWorkspaceFeedback, workspaceFeedback]);

  useEffect(() => {
    if (!highlightedMessageKey) return;
    const timer = window.setTimeout(() => setHighlightedMessageKey(""), 2400);
    return () => window.clearTimeout(timer);
  }, [highlightedMessageKey, setHighlightedMessageKey]);

  useEffect(() => {
    if (!activeSessionKey || !pendingMessageNavigation) return;
    if (pendingMessageNavigation.roleId !== activeRoleId) return;
    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 12;

    const tryHighlight = () => {
      if (cancelled) return;
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-message-key]"))
        .find((item) => item.dataset.messageKey === pendingMessageNavigation.messageKey);
      if (target) {
        setHighlightedMessageKey(pendingMessageNavigation.messageKey);
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        setPendingMessageNavigation(null);
        return;
      }
      attempts += 1;
      if (attempts >= maxAttempts) {
        setPendingMessageNavigation(null);
        return;
      }
      window.setTimeout(tryHighlight, 80);
    };

    const frame = window.requestAnimationFrame(tryHighlight);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, [
    activeRoleId,
    activeSessionKey,
    pendingMessageNavigation,
    setHighlightedMessageKey,
    setPendingMessageNavigation,
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
