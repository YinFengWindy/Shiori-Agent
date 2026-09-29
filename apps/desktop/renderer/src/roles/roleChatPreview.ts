import { normalizeSessionMediaPaths } from "../chat/chatMedia";
import { formatHourMinute } from "../shared/format";
import type { RoleLastMessage, SessionMessage } from "../shared/types";

/** One chat-list row's second line: the newest message, flattened, and when it was sent. */
export type RoleChatPreview = {
  text: string;
  timestamp: string;
};

/**
 * Flattens Markdown into one line of plain text for the chat list: fenced
 * code becomes 「[代码]」, links and images keep their text, emphasis,
 * headings, quotes, list and table markers are dropped, whitespace collapses.
 */
export function extractChatPreviewText(content: string): string {
  return content
    .replace(/```[\s\S]*?(?:```|$)/g, " [代码] ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)/gm, "")
    .replace(/^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$/gm, "")
    .replace(/\|/g, " ")
    .replace(/(\*\*|__|~~)(.*?)\1/g, "$2")
    .replace(/(^|[^\w*])[*_]([^*_\n]+)[*_](?=[^\w*]|$)/g, "$1$2")
    .replace(/\s+/g, " ")
    .trim();
}

/** Builds the preview for one message; errors and empty traces are skipped (null). */
function previewFromMessage(
  role: string,
  content: string,
  hasMedia: boolean,
  timestamp: string,
): RoleChatPreview | null {
  if (role !== "user" && role !== "assistant") return null;
  const body = extractChatPreviewText(content) || (hasMedia ? "[图片]" : "");
  if (!body) return null;
  return { text: role === "user" ? `你：${body}` : body, timestamp };
}

/** The chat-list preview from the bridge's `last_message` role field. */
export function previewFromRoleLastMessage(lastMessage: RoleLastMessage | null | undefined): RoleChatPreview | null {
  if (!lastMessage) return null;
  return previewFromMessage(lastMessage.role, lastMessage.content, lastMessage.has_media, lastMessage.timestamp);
}

/**
 * The chat-list preview from the open conversation: its newest finished user
 * or assistant message, so the active role's row follows the chat without
 * another bridge call. A reply still streaming is skipped — the row updates
 * once it lands, instead of flickering with every token.
 */
export function previewFromSessionMessages(messages: readonly SessionMessage[]): RoleChatPreview | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]!;
    if (message.streaming) continue;
    const preview = previewFromMessage(
      message.role,
      message.content,
      normalizeSessionMediaPaths(message.media).length > 0,
      message.timestamp ?? "",
    );
    if (preview) return preview;
  }
  return null;
}

const weekdayLabels = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/**
 * The day of `date` as the chat list names it relative to `now`: 「昨天」, a
 * weekday within the last week, 「9/20」 this year, 「2025/9/20」 before;
 * null for today (or a later day).
 */
export function chatListDayLabel(date: Date, now: Date): string | null {
  const dayDiff = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (dayDiff <= 0) return null;
  if (dayDiff === 1) return "昨天";
  if (dayDiff < 7) return weekdayLabels[date.getDay()]!;
  if (date.getFullYear() === now.getFullYear()) return `${date.getMonth() + 1}/${date.getDate()}`;
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
}

/**
 * Compact chat-list time: 「14:05」 today, otherwise the day
 * (`chatListDayLabel`). Empty for a missing or unreadable timestamp.
 */
export function formatChatListTime(timestamp: string, now: Date): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return chatListDayLabel(date, now) ?? formatHourMinute(date);
}
