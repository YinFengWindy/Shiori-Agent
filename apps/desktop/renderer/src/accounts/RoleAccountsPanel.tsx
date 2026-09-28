import { useState } from "react";
import { AccountDetailDialog } from "./AccountDetailDialog";
import { AccountList } from "./AccountList";
import { useAccounts } from "./useAccounts";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";

/** The selected platform detail; its account ID arrives after creation. */
type SelectedAccount = { pluginId: string; accountId: string | null };

/** The role page's 账号 tab: one row per channel, each opening its account detail. */
export function RoleAccountsPanel({ roleId }: { roleId: string }) {
  const { accounts, error, reload } = useAccounts();
  const isPluginEnabled = usePluginEnabledState();
  const [selected, setSelected] = useState<SelectedAccount | null>(null);
  const owned = accounts?.filter((item) => item.roleId === roleId) ?? null;
  const platforms = pluginUiRegistry.listAccountDetails(isPluginEnabled);
  return <div className="grid gap-3">
    <AccountList platforms={platforms} accounts={owned} error={error} onRefresh={() => void reload()}
      onOpen={(pluginId, accountId) => setSelected({ pluginId, accountId })} />
    {selected ? <AccountDetailDialog
      account={owned?.find((account) => account.id === selected.accountId) ?? null}
      pluginId={selected.pluginId}
      roleId={roleId}
      onClose={() => setSelected(null)}
      onChanged={(accountId) => {
        // A created account turns the add dialog into that account's detail.
        if (accountId) setSelected({ pluginId: selected.pluginId, accountId });
        void reload();
      }}
    /> : null}
  </div>;
}
