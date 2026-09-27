import { useState } from "react";
import { createAccountClient, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

/** Confirmation state for deleting one of a role's accounts; failures stay in the dialog. */
export function useAccountDeletion(roleId: string, onDeleted: () => void) {
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
  async function confirm() {
    if (!pending || busy) return;
    setBusy(true);
    setError("");
    try {
      await client.remove(pending.id, roleId);
      setPending(null);
      onDeleted();
    } catch (failure) {
      // The host kept the account; show why so the user can retry.
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }
  return { pending, busy, error, request, cancel, confirm };
}
