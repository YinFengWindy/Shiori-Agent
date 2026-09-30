import { createPhoneClient } from "./phoneClient";
import { usePhoneListeningUpdates } from "./usePhoneLiveUpdates";
import { usePhoneMessagePages } from "./usePhoneMessagePages";

const client = createPhoneClient();

/**
 * A group's listening records for the phone's chat page, paged by
 * `usePhoneMessagePages`, with records stored while it is open appended live. A conversation
 * that is not a group reads none (`enabled` false): an empty, complete stream.
 */
export function usePhoneListeningMessages(roleId: string, threadId: string, enabled: boolean) {
  const { pushLive, ...pages } = usePhoneMessagePages(
    `${roleId}\n${threadId}\n${enabled}`,
    (beforeSeq) => (enabled
      ? client.listListening(roleId, threadId, beforeSeq)
      : Promise.resolve({ messages: [], hasMore: false, nextBeforeSeq: null })),
  );
  usePhoneListeningUpdates(roleId, (heard) => {
    if (enabled && heard.threadId === threadId) pushLive([heard.message]);
  });
  return pages;
}
