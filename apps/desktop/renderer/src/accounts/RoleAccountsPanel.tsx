import { useState } from "react";
import { AccountDetailDialog } from "./AccountDetailDialog";
import { AccountList } from "./AccountList";
import { useAccounts } from "./useAccounts";
import { accountDeletionDescription, accountPlatformChoices } from "./accountPresentation";
import { useAccountDeletion } from "./useAccountDeletion";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";

/** A new account being added on one platform; its ID arrives once the plugin created it. */
type Adding = { pluginId: string; accountId: string | null };

/** The role page's 账号 tab: the role's accounts, adding one per platform, and deletion. */
export function RoleAccountsPanel({ roleId }: { roleId: string }) {
  const { accounts, error, reload } = useAccounts();
  const isPluginEnabled = usePluginEnabledState();
  const [choosing, setChoosing] = useState(false);
  const [adding, setAdding] = useState<Adding | null>(null);
  const deletion = useAccountDeletion(roleId, () => void reload());
  const owned = accounts?.filter((item) => item.roleId === roleId) ?? null;
  const platforms = accountPlatformChoices(pluginUiRegistry.listAccountDetails(isPluginEnabled), owned ?? []);
  return <div className="grid gap-3">
    <AccountList title="账号" roleId={roleId} accounts={owned} error={error} onRefresh={() => void reload()}
      onAdd={() => setChoosing((open) => !open)} onDelete={deletion.request} emptyLabel="暂无账号" showConnectionAction />
    {choosing ? <div className="flex flex-wrap gap-2 border-t border-line-soft pt-3" role="group" aria-label="选择平台">
      {platforms.map((platform) => <button key={platform.pluginId} type="button"
        className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} disabled={platform.bound}
        onClick={() => { setChoosing(false); setAdding({ pluginId: platform.pluginId, accountId: null }); }}>
        {platform.label}{platform.bound ? <span className="text-ink-muted">已绑定</span> : null}
      </button>)}
    </div> : null}
    {adding ? <AccountDetailDialog
      account={owned?.find((account) => account.id === adding.accountId) ?? null}
      pluginId={adding.pluginId}
      roleId={roleId}
      onClose={() => setAdding(null)}
      onChanged={(accountId) => {
        // A created account turns the add dialog into that account's detail.
        if (accountId) setAdding({ pluginId: adding.pluginId, accountId });
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
