import type { BridgeEvent } from "../../../src/bridge/shared";
import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** Whether a channel conversation is a group chat or a private one. */
export type PhoneChatType = "group" | "private";

/** Newest message of a channel conversation, as a light preview (content capped at 200 chars by the bridge). */
export type PhoneLastMessage = {
  /** `user` is the other side (anyone in the chat), `assistant` the role itself. */
  role: string;
  content: string;
  timestamp: string;
  hasMedia: boolean;
  /** The sender's platform name when the other side wrote it; null for the role's own messages or when unknown. */
  senderName: string | null;
};

/** One of the role's channel conversations, as the phone lists it. */
export type PhoneConversation = {
  threadId: string;
  /** The role's account carrying this conversation; null when the role no longer has an account on that platform. */
  accountId: string | null;
  channel: string;
  /** As the conversation's messages recorded it; null when none recorded a known type. */
  chatType: PhoneChatType | null;
  /** Group name for a group, the other person's name for a private chat (the chat ID until a name is known). */
  displayName: string;
  /** A private chat with the desktop user's own bound platform identity. */
  isUserChat: boolean;
  lastMessage: PhoneLastMessage;
};

type PhoneConversationPayload = {
  thread_id: string;
  account_id: string | null;
  channel: string;
  chat_type: PhoneChatType | null;
  display_name: string;
  is_user_chat: boolean;
  last_message: {
    role: string; content: string; timestamp: string; has_media: boolean; sender_name: string | null;
  };
};

/** One message of a conversation, from the role's point of view. */
export type PhoneMessage = {
  id: string;
  /** Store order; absent on a live row the bridge sent before it was read back. */
  seq: number | null;
  /** `role` is the role itself, `other` anyone else in the chat. */
  sender: "role" | "other";
  /** The other sender's platform ID; null for the role or when unrecorded. */
  senderId: string | null;
  /** The other sender's name as the platform reported it with this message; null for the role or when unrecorded. */
  senderName: string | null;
  /** The sender was the desktop user's bound platform identity when the message arrived. */
  senderIsUser: boolean;
  content: string;
  /** Local file paths of attached media. */
  media: string[];
  timestamp: string;
};

/** One page of a conversation, oldest first. */
export type PhoneMessagePage = {
  messages: PhoneMessage[];
  /** Older messages remain before this page. */
  hasMore: boolean;
  /** Cursor for the older page (`beforeSeq`); null when the page is empty. */
  nextBeforeSeq: number | null;
};

/** Messages newly committed to one conversation, with its refreshed list row (`phone.conversation.updated`). */
export type PhoneConversationUpdate = {
  roleId: string;
  threadId: string;
  conversation: PhoneConversation;
  messages: PhoneMessage[];
};

/** Bridge event carrying a `PhoneConversationUpdate`. */
export const phoneConversationUpdatedEvent = "phone.conversation.updated";

type PhoneMessagePayload = {
  id: string;
  seq: number | null;
  sender: "role" | "other";
  sender_id: string | null;
  sender_name: string | null;
  sender_is_user: boolean;
  content: string;
  media: string[];
  timestamp: string;
};

function mapMessage(row: PhoneMessagePayload): PhoneMessage {
  return {
    id: row.id,
    seq: row.seq,
    sender: row.sender,
    senderId: row.sender_id,
    senderName: row.sender_name,
    senderIsUser: row.sender_is_user,
    content: row.content,
    media: row.media,
    timestamp: row.timestamp,
  };
}

/** The update a `phone.conversation.updated` event carries; null for any other event. */
export function phoneConversationUpdateOf(event: BridgeEvent) {
  if (event.method !== phoneConversationUpdatedEvent) return null;
  const payload = event.payload as {
    role_id: string; thread_id: string; conversation: PhoneConversationPayload; messages: PhoneMessagePayload[];
  };
  return {
    roleId: payload.role_id,
    threadId: payload.thread_id,
    conversation: mapConversation(payload.conversation),
    messages: payload.messages.map(mapMessage),
  };
}

function mapConversation(row: PhoneConversationPayload): PhoneConversation {
  return {
    threadId: row.thread_id,
    accountId: row.account_id,
    channel: row.channel,
    chatType: row.chat_type,
    displayName: row.display_name,
    isUserChat: row.is_user_chat,
    lastMessage: {
      role: row.last_message.role,
      content: row.last_message.content,
      timestamp: row.last_message.timestamp,
      hasMedia: row.last_message.has_media,
      senderName: row.last_message.sender_name,
    },
  };
}

/** Bridge client for the phone panel's reads. */
export function createPhoneClient(invoke?: DesktopInvoke) {
  const call = <T>(method: string, payload: Record<string, unknown>) =>
    invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload);
  return {
    /** The role's channel conversations, newest message first. */
    async listConversations(roleId: string) {
      const result = await call<{ conversations: PhoneConversationPayload[] }>("phone.conversations.list", { role_id: roleId });
      return result.conversations.map(mapConversation);
    },
    /** One page of a conversation of the role, the newest one unless `beforeSeq` asks for older. */
    async listMessages(roleId: string, threadId: string, beforeSeq: number | null) {
      const result = await call<{ messages: PhoneMessagePayload[]; has_more: boolean; next_before_seq: number | null }>(
        "phone.conversation.messages",
        { role_id: roleId, thread_id: threadId, ...(beforeSeq === null ? {} : { before_seq: beforeSeq }) },
      );
      return { messages: result.messages.map(mapMessage), hasMore: result.has_more, nextBeforeSeq: result.next_before_seq };
    },
  };
}
