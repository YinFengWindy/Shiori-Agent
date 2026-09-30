import { useCallback } from "react";
import { createPhoneListeningClient } from "./phoneListeningClient";
import { usePhoneLoadedValue } from "./usePhoneLoadedValue";

const client = createPhoneListeningClient();

/**
 * A group's listening state (null while it loads). `setEnabled` and
 * `setDailyCap` change it as the user and reread it; failures propagate.
 */
export function usePhoneListening(roleId: string, threadId: string) {
  const { value, error, refresh } = usePhoneLoadedValue(
    useCallback(() => client.readState(roleId, threadId), [roleId, threadId]),
  );
  const setEnabled = useCallback(async (enabled: boolean) => {
    await client.setEnabled(roleId, threadId, enabled);
    await refresh();
  }, [roleId, threadId, refresh]);
  const setDailyCap = useCallback(async (dailyCap: number | null) => {
    await client.setDailyCap(roleId, threadId, dailyCap);
    await refresh();
  }, [roleId, threadId, refresh]);
  return { state: value, error, retry: refresh, setEnabled, setDailyCap };
}

/** The global default daily cap (null while it loads); `save` stores a new one and rereads it. */
export function usePhoneListeningDefaultCap() {
  const { value, error, refresh } = usePhoneLoadedValue(useCallback(() => client.readDefaultCap(), []));
  const save = useCallback(async (dailyCap: number) => {
    await client.saveDefaultCap(dailyCap);
    await refresh();
  }, [refresh]);
  return { defaultCap: value, error, retry: refresh, save };
}
