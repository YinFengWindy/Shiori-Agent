import { useState } from "react";
import { AccountDetailDialog } from "./AccountDetailDialog";
import { AccountList } from "./AccountList";
import { useAccounts } from "./useAccounts";
import { accountDeletionDescription } from "./accountPresentation";
import { useAccountDeletion } from "./useAccountDeletion";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";

/** The selected platform detail; its account ID arrives after creation. */
type SelectedAccount = { pluginId: string; accountId: string | null };

/** The role page's 账号 tab: the role's accounts, adding one per platform, and deletion. */
export function RoleAccountsPanel({ roleId }: { roleId: string }) {
  const { accounts, error, reload } = useAccounts();
  const isPluginEnabled = usePluginEnabledState();
  const [selected, setSelected] = useState<SelectedAccount | null>(null);
  const deletion = useAccountDeletion(roleId, () => void reload());
  const owned = accounts?.filter((item) => item.roleId === roleId) ?? null;
  const platforms = pluginUiRegistry.listAccountDetails(isPluginEnabled);
  return <div className="grid gap-3">
    <AccountList platforms={platforms} accounts={owned} error={error} onRefresh={() => void reload()}
      onOpen={(pluginId, accountId) => setSelected({ pluginId, accountId })} onDelete={deletion.request} />
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
    <ConfirmDialog
      open={Boolean(deletion.pending)}
      title="删除账号"
      persona={confirmPersonaLines.destructive}
      description={accountDeletionDescription(deletion.pending)}
      confirmLabel="确认删除"
      busy={deletion.busy}
      error={deletion.error}
      onClose={deletion.cancel}
      onConfirm={() => void deletion.confirm()}
    />
  </div>;
}
