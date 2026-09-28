import { useState } from "react";

/** Runs a platform account command and refreshes the host snapshot on success. */
export function useAccountAction(onChanged: (accountId?: string) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<string | undefined>) {
    if (busy) return false;
    setBusy(true);
    setError("");
    try {
      onChanged(await action());
      return true;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, setError, run };
}
