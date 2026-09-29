import { useCallback, useMemo, useState } from "react";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { createPhoneClient, type PhoneConversation } from "./phoneClient";
import { withLiveConversations } from "./phoneChatPresentation";
import { usePhoneLiveUpdates } from "./usePhoneLiveUpdates";

const client = createPhoneClient();

// The list is read when the phone opens; new messages then arrive as
// `phone.conversation.updated` rows (below), not as a reload.
const noRefreshEvents: ReadonlySet<string> = new Set();

/**
 * The role's channel conversations, loaded each time the phone mounts
 * (opens) or the role changes, then kept current by live updates: a
 * conversation with a new message moves to the top, a new one appears.
 */
export function usePhoneConversations(roleId: string) {
  const load = useCallback(() => client.listConversations(roleId), [roleId]);
  const { value, error, refresh } = useBridgeRefreshedValue({
    load, refreshEvents: noRefreshEvents, refreshOnFocus: false,
  });
  // The newest live row per conversation; the phone remounts per role, so these never mix roles.
  const [live, setLive] = useState<ReadonlyMap<string, PhoneConversation>>(() => new Map());
  usePhoneLiveUpdates(roleId, ({ conversation }) => {
    setLive((current) => new Map(current).set(conversation.threadId, conversation));
  });
  const conversations = useMemo(() => value && withLiveConversations(value, [...live.values()]), [value, live]);
  return { conversations, error, refresh };
}
