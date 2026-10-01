import { errorFeedback } from "../errors";
import { useCallback, useState } from "react";
import type { AccountPendingAction } from "./account";

/**
 * Runs one platform account command at a time and refreshes the host
 * snapshot on success. `pending` names the command in flight, so the status
 * card can show 正在连接 / 正在断开 before any report arrives.
 */
export function useAccountAction(onChanged: (accountId?: string) => void) {
  const [pending, setPending] = useState<AccountPendingAction | null>(null);
  const [error, setError] = useState("");
  const [errorDetail, setErrorDetail] = useState("");
  const reportError = useCallback((failure: unknown, operation: string) => {
    const view = errorFeedback(failure);
    setError(operation);
    setErrorDetail([view.message, view.detail].filter(Boolean).join("\n"));
  }, []);

  async function run(kind: AccountPendingAction, action: () => Promise<string | undefined>) {
    if (pending) return false;
    setPending(kind);
    setError("");
    try {
      onChanged(await action());
      return true;
    } catch (failure) {
      reportError(failure, kind === "connect" ? "账号连接未完成" : "账号断开未完成");
      return false;
    } finally {
      setPending(null);
    }
  }

  return { pending, busy: pending !== null, error, errorDetail, setError, reportError, run };
}
