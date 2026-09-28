import { useState } from "react";
import { createAccountClient, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

/**
 * Confirmation state for deleting one of a role's accounts; failures stay in the dialog.
 * `onSettled` reloads the list after every attempt: even a failed deletion may
 * already have disconnected the account.
 */
export function useAccountDeletion(roleId: string, onSettled: () => void) {
  const [pending, setPending] = useState<AccountSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function request(account: AccountSnapshot) {
    setPending(account);
    setError("");
  }
  function cancel() {
    if (!busy) setPending(null);
  }
  /** Deletes the pending account; resolves true once it is gone. */
  async function confirm() {
    if (!pending || busy) return false;
    setBusy(true);
    setError("");
    try {
      await client.remove(pending.id, roleId);
      setPending(null);
      return true;
    } catch (failure) {
      // The host kept the account; show why so the user can retry.
      setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally {
      setBusy(false);
      onSettled();
    }
  }
  return { pending, busy, error, request, cancel, confirm };
}
