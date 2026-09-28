import { useState } from "react";
import type { AccountPendingAction } from "./accountPresentation";

/**
 * Runs one platform account command at a time and refreshes the host
 * snapshot on success. `pending` names the command in flight, so the status
 * card can show 正在连接 / 正在断开 before any report arrives.
 */
export function useAccountAction(onChanged: (accountId?: string) => void) {
  const [pending, setPending] = useState<AccountPendingAction | null>(null);
  const [error, setError] = useState("");

  async function run(kind: AccountPendingAction, action: () => Promise<string | undefined>) {
    if (pending) return false;
    setPending(kind);
    setError("");
    try {
      onChanged(await action());
      return true;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally {
      setPending(null);
    }
  }

  return { pending, busy: pending !== null, error, setError, run };
}
