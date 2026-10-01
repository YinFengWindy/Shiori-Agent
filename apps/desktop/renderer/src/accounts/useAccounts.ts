import type { BridgeEvent } from "@shiori/sdk";
import { pluginRuntimeChanged } from "../plugins/pluginRuntimeChanged";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { createAccountClient } from "./accountClient";

const client = createAccountClient();
const loadAccounts = () => client.list();

/** The host pushes `accounts.updated` whenever a plugin's report changes an account. */
function accountsMayHaveChanged(event: BridgeEvent) {
  return event.method === "accounts.updated" || (pluginRuntimeChanged(event) && event.method !== "bridge.exit");
}

/** Keeps account snapshots current across plugin lifecycle changes, account reports, and mutations. */
export function useAccounts() {
  const { value: accounts, error, refresh: reload } = useBridgeRefreshedValue({
    load: loadAccounts, refreshEvents: accountsMayHaveChanged, refreshOnFocus: false, keepValueOnError: true,
  });
  return { accounts, error, reload, client };
}
