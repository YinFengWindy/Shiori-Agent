import { useEffect } from "react";
import { type BridgeEvent, useLatestRef } from "@shiori/sdk";
import type { PhoneConversationUpdate, PhoneListeningHeard } from "./phoneClient";
import { phoneConversationUpdateOf, phoneListeningHeardOf } from "./phonePayloads";

/**
 * Calls `onEvent` with every bridge event `parse` reads (non-null) for
 * `roleId` while mounted. A new `onEvent` identity does not resubscribe.
 */
function usePhoneRoleEvents<T extends { roleId: string }>(
  roleId: string,
  parse: (event: BridgeEvent) => T | null,
  onEvent: (value: T) => void,
) {
  const onEventRef = useLatestRef(onEvent);
  useEffect(() => window.miraDesktop.onEvent((event) => {
    const value = parse(event);
    if (value?.roleId === roleId) onEventRef.current(value);
  }), [roleId, parse, onEventRef]);
}

/**
 * Calls `onUpdate` with every `phone.conversation.updated` event for
 * `roleId` while mounted (the phone, or its chat page, is open).
 */
export function usePhoneLiveUpdates(roleId: string, onUpdate: (update: PhoneConversationUpdate) => void) {
  usePhoneRoleEvents(roleId, phoneConversationUpdateOf, onUpdate);
}

/** Calls `onHeard` with every record newly stored in one of `roleId`'s groups' listening records while mounted. */
export function usePhoneListeningUpdates(roleId: string, onHeard: (heard: PhoneListeningHeard) => void) {
  usePhoneRoleEvents(roleId, phoneListeningHeardOf, onHeard);
}
