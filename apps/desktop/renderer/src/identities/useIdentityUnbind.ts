import { useState } from "react";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { createIdentityClient, type UserIdentity } from "./identityClient";

const client = createIdentityClient();

/**
 * Confirmation state for unbinding one identity; failures stay in the dialog.
 * `onSettled` reloads the list after every attempt.
 */
export function useIdentityUnbind(onSettled: () => void) {
  const [pending, setPending] = useState<UserIdentity | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function request(identity: UserIdentity) {
    setPending(identity);
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
      await client.unbind(pending.id);
      setPending(null);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
      onSettled();
    }
  }
  return { pending, busy, error, request, cancel, confirm };
}
