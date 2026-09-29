import { formatChatListTime } from "../roles/roleChatPreview";
import { parseTimestamp } from "../shared/format";
import type { PhoneConversation, PhoneMessage } from "./phoneClient";

/** A pause longer than this between two messages gets a time separator. */
export const phoneTimeSeparatorGapMs = 5 * 60_000;

/** One line of the phone's chat page: a centered time, or a message bubble. */
export type PhoneChatItem =
  | { kind: "time"; key: string; label: string }
  | {
    kind: "message";
    key: string;
    message: PhoneMessage;
    /** The role's own messages sit on the right, everyone else's on the left. */
    side: "left" | "right";
    /** Name shown above a left bubble (the platform name, else the sender ID); null for the role or when neither is known. */
    senderLabel: string | null;
    /** The sender was the desktop user's own bound identity: their name carries the 「这是我」 badge. */
    isUser: boolean;
  };

function clockOf(date: Date) {
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

/**
 * A time separator's label: 「14:05」 today, otherwise the chat-list day
 * (「昨天」, a weekday, a date) followed by the clock, e.g. 「昨天 14:05」.
 */
export function phoneSeparatorTime(timestamp: string, now: Date) {
  const date = parseTimestamp(timestamp);
  if (!date) return "";
  const clock = clockOf(date);
  const day = formatChatListTime(timestamp, now);
  return day === clock ? clock : `${day} ${clock}`;
}

/**
 * The chat page's lines for `messages` (oldest first): a time separator
 * before the first message and after every pause longer than
 * `phoneTimeSeparatorGapMs`, then each message on its side. A message
 * without a readable time never opens a separator.
 */
export function phoneChatItems(messages: readonly PhoneMessage[], now: Date) {
  const items: PhoneChatItem[] = [];
  let previousTime: number | null = null;
  for (const message of messages) {
    const time = parseTimestamp(message.timestamp)?.getTime() ?? null;
    if (time !== null && (previousTime === null || time - previousTime > phoneTimeSeparatorGapMs)) {
      items.push({ kind: "time", key: `time:${message.id}`, label: phoneSeparatorTime(message.timestamp, now) });
    }
    if (time !== null) previousTime = time;
    const fromRole = message.sender === "role";
    items.push({
      kind: "message",
      key: message.id,
      message,
      side: fromRole ? "right" : "left",
      senderLabel: fromRole ? null : message.senderName ?? message.senderId,
      isUser: !fromRole && message.senderIsUser,
    });
  }
  return items;
}

/**
 * `first` followed by the messages of `second` it does not already hold
 * (same id). Joins an older page before the loaded ones, or live messages
 * after them; `first` itself comes back when nothing is new, so a repeated
 * live event does not re-render.
 */
export function mergePhoneMessages(first: readonly PhoneMessage[], second: readonly PhoneMessage[]) {
  const known = new Set(first.map((message) => message.id));
  const added = second.filter((message) => !known.has(message.id));
  return added.length ? [...first, ...added] : first;
}

function lastMessageTime(conversation: PhoneConversation) {
  return parseTimestamp(conversation.lastMessage.timestamp)?.getTime() ?? Number.NEGATIVE_INFINITY;
}

/**
 * The conversation list with rows that live updates brought: a live row
 * replaces the loaded row of its conversation unless the loaded one is newer,
 * a conversation not loaded yet is added, and the list is ordered newest
 * message first again (ties keep their order).
 */
export function withLiveConversations(loaded: readonly PhoneConversation[], live: readonly PhoneConversation[]) {
  if (!live.length) return loaded;
  const rows = new Map(loaded.map((conversation) => [conversation.threadId, conversation]));
  for (const conversation of live) {
    const current = rows.get(conversation.threadId);
    if (!current || lastMessageTime(conversation) >= lastMessageTime(current)) rows.set(conversation.threadId, conversation);
  }
  // Two unreadable times subtract to NaN: keep their order.
  return [...rows.values()].sort((left, right) => (lastMessageTime(right) - lastMessageTime(left)) || 0);
}
