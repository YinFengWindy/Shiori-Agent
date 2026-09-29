import type { PhoneChatItem } from "./phoneChatPresentation";
import type { PhoneConversation } from "./phoneClient";
import type { PhoneMember } from "./phoneMemoryClient";
import type { PhoneApp } from "./phonePresentation";

/**
 * Blocks of a conversation's chat info page. The page renders them in the
 * order `phoneChatInfoSections` lists them, each id through its registered
 * view; a later block (e.g. listening in on a group) adds an id here, a
 * descriptor there and a view in the page's registry.
 */
export type PhoneChatInfoSectionId = "summary" | "members" | "note" | "activity";

/** One block of the chat info page. */
export type PhoneChatInfoSection = {
  id: PhoneChatInfoSectionId;
  title: string;
};

/**
 * The chat info page's blocks for `conversation`: none for the bound user's
 * own private chat (it is user context, with no group memory; the desktop
 * conversation never reaches the phone), otherwise the conversation summary,
 * its members, the note (editable) and the recent activity (read-only:
 * only memory consolidation writes it). A stranger's private chat is external too
 * and gets the same blocks, titled for a chat rather than a group.
 */
export function phoneChatInfoSections(conversation: Pick<PhoneConversation, "isUserChat" | "chatType">): PhoneChatInfoSection[] {
  if (conversation.isUserChat) return [];
  const group = conversation.chatType === "group";
  return [
    { id: "summary", title: group ? "群信息" : "聊天信息" },
    { id: "members", title: group ? "群成员" : "成员" },
    { id: "note", title: group ? "群笔记" : "笔记" },
    { id: "activity", title: "最近动态" },
  ];
}

/** The summary block's rows: who or which group, the channel, and the role's account carrying it. */
export function phoneChatSummaryRows(
  conversation: Pick<PhoneConversation, "chatType" | "displayName">,
  app: Pick<PhoneApp, "label" | "accountName">,
) {
  return [
    { label: conversation.chatType === "group" ? "群名" : "对方", value: conversation.displayName },
    { label: "渠道", value: app.label },
    { label: "经由账号", value: app.accountName },
  ];
}

/**
 * The member whose profile a chat line's avatar opens (their sender ID);
 * null when it opens none: the role's own lines, the user's (the user has
 * no member profile), a sender whose ID was not recorded, and any line of a
 * conversation without a chat info page.
 */
export function phoneMemberEntryOf(
  item: Extract<PhoneChatItem, { kind: "message" }>,
  conversation: Pick<PhoneConversation, "isUserChat" | "chatType">,
) {
  const { message } = item;
  if (!phoneChatInfoSections(conversation).length || message.sender === "role" || item.isUser) return null;
  return message.senderId;
}

/**
 * A screen stacked over a conversation's chat page: its chat info page, or
 * a member's profile opened from a chat avatar (`from: "chat"`) or from the
 * info page's member list (`from: "info"`).
 */
export type PhoneChatSubpage = { kind: "info" } | { kind: "member"; senderId: string; from: "chat" | "info" };

/** Where the back button of `page` goes: the info page for a profile opened from it, else the chat page (null). */
export function phoneSubpageBack(page: PhoneChatSubpage): PhoneChatSubpage | null {
  return page.kind === "member" && page.from === "info" ? { kind: "info" } : null;
}

/** The editable fields of a member profile; the nickname history is kept by the host. */
export type PhoneMemberDraft = Pick<PhoneMember, "brief" | "profile">;

/** A member profile draft differs from the stored profile. */
export function memberDraftDirty(draft: PhoneMemberDraft, member: PhoneMemberDraft) {
  return draft.brief !== member.brief || draft.profile !== member.profile;
}
