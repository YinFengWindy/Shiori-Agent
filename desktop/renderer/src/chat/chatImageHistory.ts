import type { SessionPayload } from "../shared/types";

export type ChatImageHistoryEntry = {
  path: string;
  messageId: string;
  mediaIndex: number;
  timestamp: string | null;
};

const supportedImageExtensions = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]);

/** Returns whether a media path points to a chat image asset that can be previewed in the sidebar. */
export function isChatImageAsset(path: string): boolean {
  const cleanPath = path.split(/[?#]/)[0] ?? "";
  const dotIndex = cleanPath.lastIndexOf(".");
  const extension = dotIndex >= 0 ? cleanPath.slice(dotIndex).toLowerCase() : "";
  return supportedImageExtensions.has(extension);
}

/** Collects every image that appeared in the current chat session, preserving message order. */
export function collectChatImageHistory(session: SessionPayload | null): ChatImageHistoryEntry[] {
  if (!session) {
    return [];
  }

  const history: ChatImageHistoryEntry[] = [];
  for (let messageIndex = 0; messageIndex < session.messages.length; messageIndex += 1) {
    const message = session.messages[messageIndex];
    const media = Array.isArray(message?.media) ? message.media : [];
    for (let mediaIndex = 0; mediaIndex < media.length; mediaIndex += 1) {
      const path = String(media[mediaIndex] ?? "").trim();
      if (!path || !isChatImageAsset(path)) {
        continue;
      }
      history.push({
        path,
        messageId: String(message.id ?? `${message.role}-${messageIndex}`),
        mediaIndex,
        timestamp: message.timestamp ?? null,
      });
    }
  }
  return history;
}

/** Keeps the current selection when possible and otherwise falls back to the newest chat image. */
export function resolveChatImageSelection(
  history: ChatImageHistoryEntry[],
  selectedPath: string,
): string {
  if (history.length === 0) {
    return "";
  }
  if (selectedPath && history.some((entry) => entry.path === selectedPath)) {
    return selectedPath;
  }
  return history[history.length - 1]?.path ?? "";
}

/** Finds the selected image index and falls back to the newest history item when the path is missing. */
export function findChatImageHistoryIndex(
  history: ChatImageHistoryEntry[],
  selectedPath: string,
): number {
  if (history.length === 0) {
    return -1;
  }
  if (!selectedPath) {
    return history.length - 1;
  }
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index]?.path === selectedPath) {
      return index;
    }
  }
  return history.length - 1;
}

/** Returns the history entry for the selected chat image path so callers can navigate back to its source message. */
export function findChatImageHistoryEntry(
  history: ChatImageHistoryEntry[],
  selectedPath: string,
): ChatImageHistoryEntry | null {
  if (!selectedPath) {
    return null;
  }
  return history.find((entry) => entry.path === selectedPath) ?? null;
}
