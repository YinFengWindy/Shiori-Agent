import { createPhoneClient } from "./phoneClient";
import { usePhoneLiveUpdates } from "./usePhoneLiveUpdates";
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
