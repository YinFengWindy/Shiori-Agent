import { useMemo } from "react";
import type { PhoneConversation } from "./phoneClient";
import { phoneChatTimeline } from "./phoneChatTimeline";
import { usePhoneChatMessages } from "./usePhoneChatMessages";
import { usePhoneListeningMessages } from "./usePhoneListeningMessages";

/**
 * The chat page's messages: the conversation, and for a group its
 * listening records too, merged by `phoneChatTimeline` (null until both
 * newest pages arrive). `loadOlder` pages the stream that bounds what
 * shows; `retry` reloads whichever stream failed.
 */
export function usePhoneChatTimeline(roleId: string, conversation: Pick<PhoneConversation, "threadId" | "chatType">) {
  const said = usePhoneChatMessages(roleId, conversation.threadId);
  const heard = usePhoneListeningMessages(roleId, conversation.threadId, conversation.chatType === "group");
  const timeline = useMemo(() => (said.messages && heard.messages
    ? phoneChatTimeline({ messages: said.messages, hasMore: said.hasMore }, { messages: heard.messages, hasMore: heard.hasMore })
    : null), [said.messages, said.hasMore, heard.messages, heard.hasMore]);
  const failed = [said, heard].filter((stream) => stream.error);
  return {
    messages: timeline?.messages ?? null,
    hasMore: timeline?.hasMore ?? false,
    error: failed[0]?.error ?? "",
    loadOlder: timeline?.olderFrom === "listening" ? heard.loadOlder : said.loadOlder,
    retry: () => failed.forEach((stream) => stream.retry()),
  };
}
