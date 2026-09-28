import { useEffect, useState } from "react";
import { createAccountClient, type AccountSnapshot } from "./accountClient";

const client = createAccountClient();

/** Accounts a role deletion also deletes, or why they could not be listed. */
export type RoleDeletionAccounts = { accounts: AccountSnapshot[]; error: string };

const NONE: RoleDeletionAccounts = { accounts: [], error: "" };

/**
 * The accounts deleting `roleId` also deletes: those its loaded plugins hold.
 * Empty while no role is pending or the list is still loading.
 */
export function useRoleDeletionAccounts(roleId: string | null): RoleDeletionAccounts {
  const [loaded, setLoaded] = useState<{ roleId: string; result: RoleDeletionAccounts } | null>(null);
  useEffect(() => {
    if (!roleId) return;
    let active = true;
    client.list(roleId).then(
      (accounts) => { if (active) setLoaded({ roleId, result: { accounts, error: "" } }); },
      (failure: unknown) => {
        if (active) setLoaded({ roleId, result: { accounts: [], error: failure instanceof Error ? failure.message : String(failure) } });
      },
    );
    return () => { active = false; };
  }, [roleId]);
  return roleId && loaded?.roleId === roleId ? loaded.result : NONE;
}
