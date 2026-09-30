import { createPhoneClient } from "./phoneClient";
import { usePhoneListeningUpdates, usePhoneLiveUpdates } from "./usePhoneLiveUpdates";
import { usePhoneMessagePages } from "./usePhoneMessagePages";

const client = createPhoneClient();

/**
 * One conversation's messages for the phone's chat page, paged by
 * `usePhoneMessagePages`, with messages committed while it is open
 * appended live.
 */
export function usePhoneChatMessages(roleId: string, threadId: string) {
  const { pushLive, ...pages } = usePhoneMessagePages(
    `${roleId}\n${threadId}`,
    (beforeSeq) => client.listMessages(roleId, threadId, beforeSeq),
  );
  usePhoneLiveUpdates(roleId, (update) => {
    if (update.threadId === threadId) pushLive(update.messages);
  });
  return pages;
}

/**
 * A group's listening records for the phone's chat page, paged the same
 * way, with records stored while it is open appended live. A conversation
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
