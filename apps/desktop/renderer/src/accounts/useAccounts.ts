import { useCallback, useEffect, useRef, useState } from "react";
import { pluginRuntimeChanged } from "../plugins/pluginRuntimeChanged";
import { createAccountClient, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

/** Keeps account snapshots current across plugin lifecycle changes, account reports, and mutations. */
export function useAccounts() {
  const [accounts, setAccounts] = useState<AccountSnapshot[] | null>(null);
  const [error, setError] = useState("");
  const request = useRef(0);
  const reload = useCallback(async () => {
    const current = ++request.current;
    try {
      const next = await client.list();
      if (current === request.current) { setAccounts(next); setError(""); }
    } catch (failure) {
      if (current === request.current) setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  // The host pushes `accounts.updated` whenever a plugin's report changes an account.
  useEffect(() => window.miraDesktop.onEvent((event) => {
    if (event.method === "accounts.updated" || (pluginRuntimeChanged(event) && event.method !== "bridge.exit")) void reload();
  }), [reload]);
  return { accounts, error, reload, client };
}
