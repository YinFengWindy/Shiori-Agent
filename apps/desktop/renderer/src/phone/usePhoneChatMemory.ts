import { useCallback } from "react";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { createPhoneMemoryClient, type PhoneMember } from "./phoneMemoryClient";

const client = createPhoneMemoryClient();

// Read when a chat info screen opens; memory consolidation pushes no event,
// so a screen shows what was stored when it opened.
const noRefreshEvents: ReadonlySet<string> = new Set();

/** A value read once per mount (or when `load` changes); `refresh` reads it again. */
function usePhoneLoadedValue<T>(load: () => Promise<T>) {
  return useBridgeRefreshedValue({ load, refreshEvents: noRefreshEvents, refreshOnFocus: false });
}

/**
 * A conversation's group note (null while it loads). `save` stores a new
 * note and rereads it; failures propagate.
 */
export function usePhoneGroupNote(roleId: string, threadId: string) {
  const { value, error, refresh } = usePhoneLoadedValue(
    useCallback(() => client.readNote(roleId, threadId), [roleId, threadId]),
  );
  const save = useCallback(async (note: string) => {
    await client.saveNote(roleId, threadId, note);
    await refresh();
  }, [roleId, threadId, refresh]);
  return { note: value, error, retry: refresh, save };
}

/** A conversation's recent activity (null while it loads); read-only. */
export function usePhoneRecentActivity(roleId: string, threadId: string) {
  const { value, error, refresh } = usePhoneLoadedValue(
    useCallback(() => client.readRecentActivity(roleId, threadId), [roleId, threadId]),
  );
  return { activity: value, error, retry: refresh };
}

/** The profiled members who spoke in a conversation (null while they load). */
export function usePhoneMembers(roleId: string, threadId: string) {
  const { value, error, refresh } = usePhoneLoadedValue(
    useCallback(() => client.listMembers(roleId, threadId), [roleId, threadId]),
  );
  return { members: value, error, retry: refresh };
}

/**
 * One member's profile, opened from a conversation: null while it loads,
 * then `{ member }` with `member` null when the role has none for them.
 * `save` stores the editable fields and rereads the profile; `remove`
 * deletes it. Failures propagate to the caller.
 */
export function usePhoneMemberProfile(roleId: string, threadId: string, senderId: string) {
  const { value, error, refresh } = usePhoneLoadedValue(
    useCallback(async () => ({ member: await client.readMember(roleId, threadId, senderId) }), [roleId, threadId, senderId]),
  );
  const save = useCallback(async (fields: Pick<PhoneMember, "brief" | "profile">) => {
    await client.saveMember(roleId, threadId, senderId, fields);
    await refresh();
  }, [roleId, threadId, senderId, refresh]);
  const remove = useCallback(() => client.deleteMember(roleId, threadId, senderId), [roleId, threadId, senderId]);
  return { profile: value, error, retry: refresh, save, remove };
}
