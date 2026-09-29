import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** What the role remembers about one member of its external conversations (their profile). */
export type PhoneMember = {
  channel: string;
  /** The member's platform ID on `channel`. */
  senderId: string;
  /** The most recently used nickname, or the ID when none was recorded. */
  callName: string;
  /** Every nickname seen, most recently used last; kept by the host, read-only. */
  nicknames: string[];
  /** One-line note. */
  brief: string;
  /** Full profile text (Markdown). */
  profile: string;
};

/** A member profile as the bridge sends it. */
type PhoneMemberPayload = {
  channel: string; sender_id: string; call_name: string; nicknames: string[]; brief: string; profile: string;
};

function mapMember(row: PhoneMemberPayload) {
  return {
    channel: row.channel,
    senderId: row.sender_id,
    callName: row.call_name,
    nicknames: row.nicknames,
    brief: row.brief,
    profile: row.profile,
  } satisfies PhoneMember;
}

/**
 * Bridge client for the phone's chat info page: the role's memory of one
 * external conversation (`threadId`) and of the members it met there. A
 * member is named by `senderId` on that conversation's channel.
 */
export function createPhoneMemoryClient(invoke?: DesktopInvoke) {
  const call = <T>(method: string, payload: Record<string, unknown>) =>
    invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload);
  return {
    /** The conversation's group note (Markdown); `""` when there is none. */
    async readNote(roleId: string, threadId: string) {
      const result = await call<{ note: string }>("phone.conversation.note", { role_id: roleId, thread_id: threadId });
      return result.note;
    },
    /** Replaces the group note (a blank one removes it); resolves to the stored note. */
    async saveNote(roleId: string, threadId: string, note: string) {
      const result = await call<{ note: string }>("phone.conversation.note.save", { role_id: roleId, thread_id: threadId, note });
      return result.note;
    },
    /** The conversation's recent activity, written only by memory consolidation; `""` when there is none. */
    async readRecentActivity(roleId: string, threadId: string) {
      const result = await call<{ recent_activity: string }>("phone.conversation.activity", { role_id: roleId, thread_id: threadId });
      return result.recent_activity;
    },
    /** Profiled members who spoke in the conversation, by name; never the user. */
    async listMembers(roleId: string, threadId: string) {
      const result = await call<{ members: PhoneMemberPayload[] }>("phone.conversation.members", { role_id: roleId, thread_id: threadId });
      return result.members.map(mapMember);
    },
    /** One member's profile; null when the role has none for them. */
    async readMember(roleId: string, threadId: string, senderId: string) {
      const result = await call<{ member: PhoneMemberPayload | null }>(
        "phone.member.profile", { role_id: roleId, thread_id: threadId, sender_id: senderId },
      );
      return result.member && mapMember(result.member);
    },
    /** Rewrites an existing profile's brief and full text; resolves to the stored profile. */
    async saveMember(roleId: string, threadId: string, senderId: string, fields: Pick<PhoneMember, "brief" | "profile">) {
      const result = await call<{ member: PhoneMemberPayload }>("phone.member.profile.save", {
        role_id: roleId, thread_id: threadId, sender_id: senderId, brief: fields.brief, profile: fields.profile,
      });
      return mapMember(result.member);
    },
    /** Deletes a member's profile. */
    async deleteMember(roleId: string, threadId: string, senderId: string) {
      await call<{ sender_id: string }>("phone.member.profile.delete", { role_id: roleId, thread_id: threadId, sender_id: senderId });
    },
  };
}
