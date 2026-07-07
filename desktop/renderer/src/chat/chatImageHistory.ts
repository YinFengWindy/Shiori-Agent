import type { SessionPayload } from "../shared/types";
import { normalizeSessionMediaPaths } from "./chatMedia";

export type ChatImageHistoryEntry = {
  historyKey: string;
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

/** Builds a stable history identity for one media item inside a chat message. */
export function buildChatImageHistoryKey(messageId: string, mediaIndex: number): string {
  return `${messageId}:${mediaIndex}`;
}

/** Collects every image that appeared in the current chat session, preserving message order. */
export function collectChatImageHistory(session: SessionPayload | null): ChatImageHistoryEntry[] {
  if (!session) {
    return [];
  }

  const history: ChatImageHistoryEntry[] = [];
  for (let messageIndex = 0; messageIndex < session.messages.length; messageIndex += 1) {
    const message = session.messages[messageIndex];
    const media = normalizeSessionMediaPaths(message?.media);
    for (let mediaIndex = 0; mediaIndex < media.length; mediaIndex += 1) {
      const path = String(media[mediaIndex] ?? "").trim();
      if (!path || !isChatImageAsset(path)) {
        continue;
      }
      const messageId = String(message.id ?? `${message.role}-${messageIndex}`);
      history.push({
        historyKey: buildChatImageHistoryKey(messageId, mediaIndex),
        path,
        messageId,
        mediaIndex,
        timestamp: message.timestamp ?? null,
      });
    }
  }
  return history;
}

/** Keeps the current selection when possible and otherwise falls back to the newest chat image. */
export function resolveChatImageSelectionKey(
  history: ChatImageHistoryEntry[],
  selectedHistoryKey: string,
): string {
  if (history.length === 0) {
    return "";
  }
  if (selectedHistoryKey && history.some((entry) => entry.historyKey === selectedHistoryKey)) {
    return selectedHistoryKey;
  }
  return history[history.length - 1]?.historyKey ?? "";
}

/** Finds the selected image index and falls back to the newest history item when the path is missing. */
export function findChatImageHistoryIndex(
  history: ChatImageHistoryEntry[],
  selectedHistoryKey: string,
): number {
  if (history.length === 0) {
    return -1;
  }
  if (!selectedHistoryKey) {
    return history.length - 1;
  }
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index]?.historyKey === selectedHistoryKey) {
      return index;
    }
  }
  return history.length - 1;
}

/** Returns the history entry for the selected chat image path so callers can navigate back to its source message. */
export function findChatImageHistoryEntry(
  history: ChatImageHistoryEntry[],
  selectedHistoryKey: string,
): ChatImageHistoryEntry | null {
  if (!selectedHistoryKey) {
    return null;
  }
  return history.find((entry) => entry.historyKey === selectedHistoryKey) ?? null;
}
