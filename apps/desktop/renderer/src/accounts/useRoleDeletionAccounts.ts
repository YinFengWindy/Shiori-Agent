import { useEffect, useState } from "react";
import type { AccountSnapshot } from "@shiori/plugin-sdk";
import { createAccountClient } from "./accountClient";

const client = createAccountClient();

/** Accounts a role deletion also deletes, or why they could not be listed. */
export type RoleDeletionAccounts = { accounts: AccountSnapshot[]; error: string; status: "loading" | "ready" | "error" };

const LOADING: RoleDeletionAccounts = { accounts: [], error: "", status: "loading" };

/**
 * The accounts deleting `roleId` also deletes: those its loaded plugins hold.
 * Empty while no role is pending or the list is still loading.
 */
export function useRoleDeletionAccounts(roleId: string | null) {
  const [loaded, setLoaded] = useState<{ roleId: string; result: RoleDeletionAccounts } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!roleId) {
      setLoaded(null);
      return;
    }
    let active = true;
    client.list(roleId).then(
      (accounts) => { if (active) setLoaded({ roleId, result: { accounts, error: "", status: "ready" } }); },
      (failure: unknown) => {
        if (active) setLoaded({ roleId, result: { accounts: [], error: failure instanceof Error ? failure.message : String(failure), status: "error" } });
      },
    );
    return () => { active = false; };
  }, [roleId, attempt]);
  const result = roleId && loaded?.roleId === roleId ? loaded.result : LOADING;
  return { ...result, retry: () => { setLoaded(null); setAttempt((current) => current + 1); } };
}
