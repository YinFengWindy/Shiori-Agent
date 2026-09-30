import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";
import { mapConversation, mapMessage, type PhoneConversationPayload, type PhoneMessagePayload } from "./phonePayloads";

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
  /** Local file of the cached platform avatar: the group's, or the other person's for a private chat; null when none is cached. */
  avatarPath: string | null;
  /** A private chat with the desktop user's own bound platform identity. */
  isUserChat: boolean;
  /** A group on a channel whose plugin declares listening: its chat info page has the 旁听 block. */
  listeningSupported: boolean;
  lastMessage: PhoneLastMessage;
};

/** One message of a conversation, from the role's point of view. */
/** A member a message @s: the platform ID, and a name when the bridge knows one (the role's account name, else the member's recorded name). */
export type PhoneMention = { id: string; name: string | null };

/** The message a message quotes (#555): its sender, named like a mention, and its text and pictures. */
export type PhoneQuote = {
  senderId: string | null;
  name: string | null;
  content: string;
  /** Local file paths of the quoted message's pictures, apart from the message's own `media`. */
  media: string[];
};

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
  /** The sender is the desktop user: a binding recognises them now (read time, not when the message arrived). */
  senderIsUser: boolean;
  /** Local file of the other sender's cached platform avatar; null for the role or when none is cached. */
  senderAvatarPath: string | null;
  /** Members the group message structurally @s, in order (#553); empty for none. */
  mentions: PhoneMention[];
  /** The message this one quotes; null for none. */
  quote: PhoneQuote | null;
  content: string;
  /** Local file paths of attached media. */
  media: string[];
  timestamp: string;
  /** Heard while listening in on the group (#538), not said to the role; `seq` then orders the group's listening records. */
  listened: boolean;
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

/** A message newly stored in a group's listening records (`phone.listening.heard`). */
export type PhoneListeningHeard = {
  roleId: string;
  threadId: string;
  message: PhoneMessage;
};

/** Bridge client for the phone panel's reads. */
export function createPhoneClient(invoke?: DesktopInvoke) {
  const call = <T>(method: string, payload: Record<string, unknown>) =>
    invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload);
  const page = async (method: string, roleId: string, threadId: string, beforeSeq: number | null): Promise<PhoneMessagePage> => {
    const result = await call<{ messages: PhoneMessagePayload[]; has_more: boolean; next_before_seq: number | null }>(
      method, { role_id: roleId, thread_id: threadId, ...(beforeSeq === null ? {} : { before_seq: beforeSeq }) },
    );
    return { messages: result.messages.map(mapMessage), hasMore: result.has_more, nextBeforeSeq: result.next_before_seq };
  };
  return {
    /** The role's channel conversations, newest message first. */
    async listConversations(roleId: string) {
      const result = await call<{ conversations: PhoneConversationPayload[] }>("phone.conversations.list", { role_id: roleId });
      return result.conversations.map(mapConversation);
    },
    /** One page of a conversation of the role, the newest one unless `beforeSeq` asks for older. */
    listMessages(roleId: string, threadId: string, beforeSeq: number | null) {
      return page("phone.conversation.messages", roleId, threadId, beforeSeq);
    },
    /** One page of a group's listening records (kept after listening is turned off), the newest one unless `beforeSeq` asks for older. */
    listListening(roleId: string, threadId: string, beforeSeq: number | null) {
      return page("phone.listening.messages", roleId, threadId, beforeSeq);
    },
  };
}
