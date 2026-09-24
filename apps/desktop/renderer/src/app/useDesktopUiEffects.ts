import { useEffect } from "react";
import type React from "react";

type UseDesktopUiEffectsArgs = {
  pendingMessageNavigation: { roleId: string; messageKey: string } | null;
  setHighlightedMessageKey: React.Dispatch<React.SetStateAction<string>>;
  highlightedMessageKey: string;
  previewIllustrations: string[];
  activeIllustration: string;
  persistedChatBackground: string;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
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

/** Runs UI-only desktop effects such as message highlight retries and illustration fallback. */
export function useDesktopUiEffects({
  pendingMessageNavigation,
  setHighlightedMessageKey,
  highlightedMessageKey,
  previewIllustrations,
  activeIllustration,
  persistedChatBackground,
  setActiveIllustration,
}: UseDesktopUiEffectsArgs) {
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
