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
  };
}
