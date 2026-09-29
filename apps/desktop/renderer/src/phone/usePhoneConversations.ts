import { useCallback } from "react";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { createPhoneClient } from "./phoneClient";

const client = createPhoneClient();

// The list is read when the phone opens; following new messages live is the
// phone chat page's job (#485), so no bridge event refreshes it.
const noRefreshEvents: ReadonlySet<string> = new Set();

/** The role's channel conversations, loaded each time the phone mounts (opens) or the role changes. */
export function usePhoneConversations(roleId: string) {
  const load = useCallback(() => client.listConversations(roleId), [roleId]);
  const { value, error, refresh } = useBridgeRefreshedValue({
    load, refreshEvents: noRefreshEvents, refreshOnFocus: false,
  });
  return { conversations: value, error, refresh };
}
