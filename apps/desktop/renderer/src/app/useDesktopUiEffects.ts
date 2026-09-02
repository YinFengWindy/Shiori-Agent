import { useEffect } from "react";
import type React from "react";
import { findChatMessageElement } from "../chat/chatMessageDom";
import { watchForChatMessageTarget } from "../chat/chatMessageNavigation";
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
    if (
      pendingMessageNavigation
      && pendingMessageNavigation.roleId === activeRoleId
      && pendingMessageNavigation.messageKey === highlightedMessageKey
    ) {
      return;
    }
    const timer = window.setTimeout(() => setHighlightedMessageKey(""), 2400);
    return () => window.clearTimeout(timer);
  }, [
    activeRoleId,
    highlightedMessageKey,
    pendingMessageNavigation,
    setHighlightedMessageKey,
  ]);

  useEffect(() => {
    if (!pendingMessageNavigation) return;
    if (!activeSessionKey || pendingMessageNavigation.roleId !== activeRoleId) {
      setPendingMessageNavigation(null);
      return;
    }
    const messageKey = pendingMessageNavigation.messageKey;
    // Highlighting pins an offscreen virtualized row into the DOM. The watcher
    // then waits for that render instead of expiring after a timing guess.
    setHighlightedMessageKey(messageKey);
    return watchForChatMessageTarget({
      findTarget: () => findChatMessageElement(messageKey),
      onTarget: (target) => {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        setPendingMessageNavigation(null);
      },
      requestAnimationFrame: window.requestAnimationFrame.bind(window),
      cancelAnimationFrame: window.cancelAnimationFrame.bind(window),
      setTimeout: window.setTimeout.bind(window),
      clearTimeout: window.clearTimeout.bind(window),
      observeMutations: (callback) => {
        if (typeof MutationObserver === "undefined" || !document.body) {
          return () => undefined;
        }
        const observer = new MutationObserver(callback);
        observer.observe(document.body, { childList: true, subtree: true });
        return () => observer.disconnect();
      },
    });
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
