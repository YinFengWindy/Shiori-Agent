import type { BridgeEvent } from "@shiori/plugin-sdk";
import { isRecord } from "../shared/isRecord";
import type { PhoneChatType, PhoneConversation, PhoneConversationUpdate, PhoneMessage } from "./phoneClient";

/** A conversation list row as the bridge sends it (`phone.conversations.list`, live updates). */
export type PhoneConversationPayload = {
  thread_id: string;
  account_id: string | null;
  channel: string;
  chat_type: PhoneChatType | null;
  display_name: string;
  avatar_abs: string | null;
  is_user_chat: boolean;
  last_message: {
    role: string; content: string; timestamp: string; has_media: boolean; sender_name: string | null;
  };
};

/** A conversation message as the bridge sends it (`phone.conversation.messages`, live updates). */
export type PhoneMessagePayload = {
  id: string;
  seq: number | null;
  sender: "role" | "other";
  sender_id: string | null;
  sender_name: string | null;
  sender_is_user: boolean;
  sender_avatar_abs: string | null;
  content: string;
  media: string[];
  timestamp: string;
};

/** Bridge event carrying a `PhoneConversationUpdate`. */
const phoneConversationUpdatedEvent = "phone.conversation.updated";

function isText(value: unknown): value is string {
  return typeof value === "string";
}

function isTextOrNull(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isLastMessagePayload(value: unknown): value is PhoneConversationPayload["last_message"] {
  return isRecord(value) && isText(value.role) && isText(value.content) && isText(value.timestamp)
    && typeof value.has_media === "boolean" && isTextOrNull(value.sender_name);
}

function isConversationPayload(value: unknown): value is PhoneConversationPayload {
  return isRecord(value) && isText(value.thread_id) && isTextOrNull(value.account_id) && isText(value.channel)
    && (value.chat_type === "group" || value.chat_type === "private" || value.chat_type === null)
    && isText(value.display_name) && isTextOrNull(value.avatar_abs) && typeof value.is_user_chat === "boolean"
    && isLastMessagePayload(value.last_message);
}

function isMessagePayload(value: unknown): value is PhoneMessagePayload {
  return isRecord(value) && isText(value.id) && (value.seq === null || typeof value.seq === "number")
    && (value.sender === "role" || value.sender === "other") && isTextOrNull(value.sender_id)
    && isTextOrNull(value.sender_name) && typeof value.sender_is_user === "boolean"
    && isTextOrNull(value.sender_avatar_abs) && isText(value.content)
    && Array.isArray(value.media) && value.media.every(isText) && isText(value.timestamp);
}

/** A bridge list row in the renderer's shape. */
export function mapConversation(row: PhoneConversationPayload) {
  return {
    threadId: row.thread_id,
    accountId: row.account_id,
    channel: row.channel,
    chatType: row.chat_type,
    displayName: row.display_name,
    avatarPath: row.avatar_abs,
    isUserChat: row.is_user_chat,
    lastMessage: {
      role: row.last_message.role,
      content: row.last_message.content,
      timestamp: row.last_message.timestamp,
      hasMedia: row.last_message.has_media,
      senderName: row.last_message.sender_name,
    },
  } satisfies PhoneConversation;
}

/** A bridge message row in the renderer's shape. */
export function mapMessage(row: PhoneMessagePayload) {
  return {
    id: row.id,
    seq: row.seq,
    sender: row.sender,
    senderId: row.sender_id,
    senderName: row.sender_name,
    senderIsUser: row.sender_is_user,
    senderAvatarPath: row.sender_avatar_abs,
    content: row.content,
    media: row.media,
    timestamp: row.timestamp,
  } satisfies PhoneMessage;
}

/**
 * The update a `phone.conversation.updated` event carries; null for any
 * other event. A payload without the update's shape is a bridge contract
 * break and throws.
 */
export function phoneConversationUpdateOf(event: BridgeEvent) {
  if (event.method !== phoneConversationUpdatedEvent) return null;
  const { role_id: roleId, thread_id: threadId, conversation, messages } = event.payload;
  if (!isText(roleId) || !isText(threadId) || !isConversationPayload(conversation)
    || !Array.isArray(messages) || !messages.every(isMessagePayload)) {
    throw new Error(`${phoneConversationUpdatedEvent} 的负载格式不符`);
  }
  return {
    roleId, threadId, conversation: mapConversation(conversation), messages: messages.map(mapMessage),
  } satisfies PhoneConversationUpdate;
}
