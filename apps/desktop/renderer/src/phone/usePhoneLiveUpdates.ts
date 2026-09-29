import { useEffect } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import { phoneConversationUpdateOf, type PhoneConversationUpdate } from "./phoneClient";

/**
 * Calls `onUpdate` with every `phone.conversation.updated` event for
 * `roleId` while mounted (the phone, or its chat page, is open). A new
 * `onUpdate` identity does not resubscribe.
 */
export function usePhoneLiveUpdates(roleId: string, onUpdate: (update: PhoneConversationUpdate) => void) {
  const onUpdateRef = useLatestRef(onUpdate);
  useEffect(() => window.miraDesktop.onEvent((event) => {
    const update = phoneConversationUpdateOf(event);
    if (update?.roleId === roleId) onUpdateRef.current(update);
  }), [roleId, onUpdateRef]);
}
