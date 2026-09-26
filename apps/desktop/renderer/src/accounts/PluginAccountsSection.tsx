import { useState } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { AccountDetailDialog } from "./AccountDetailDialog";
import { AccountList } from "./AccountList";
import { useAccounts } from "./useAccounts";

/** Plugin settings entry for all accounts provided by one plugin. */
export function PluginAccountsSection({ pluginId }: { pluginId: string }) {
  const { accounts, error, reload } = useAccounts();
  const [adding, setAdding] = useState(false);
  const own = accounts?.filter((account) => account.pluginId === pluginId) ?? null;
  const canAdd = Boolean(pluginUiRegistry.getAccountDetail(pluginId, () => true));
  if (!canAdd && !own?.length) return null;
  return <>
    <AccountList title="账号" accounts={own} error={error} onRefresh={() => void reload()} onAdd={canAdd ? () => setAdding(true) : undefined} emptyLabel="暂无账号" showOwner />
    {adding ? <AccountDetailDialog account={null} pluginId={pluginId} onClose={() => setAdding(false)} onChanged={() => { void reload(); setAdding(false); }} /> : null}
  </>;
}
