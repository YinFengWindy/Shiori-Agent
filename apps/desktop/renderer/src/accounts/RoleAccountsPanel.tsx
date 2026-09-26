import { useState } from "react";
import { AccountList } from "./AccountList";
import { useAccounts } from "./useAccounts";
import { accountStatus } from "./accountPresentation";
import { createAccountClient } from "./accountClient";
import { InlineError } from "../shared/feedback/InlineError";
import { ghostButtonClass } from "../shared/styles";

const client = createAccountClient();

/** Role's owned accounts and unclaimed account picker. */
export function RoleAccountsPanel({ roleId, onOpenPluginSettings }: {
  roleId: string;
  onOpenPluginSettings: (pluginId: string | null) => void;
}) {
  const { accounts, error, reload } = useAccounts();
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState("");
  const owned = accounts?.filter((item) => item.roleId === roleId) ?? null;
  const unclaimed = accounts?.filter((item) => item.roleId === null) ?? [];
  return <div className="grid gap-3">
    <AccountList title="账号" accounts={owned} error={error} onRefresh={() => void reload()} onAdd={() => { if (unclaimed.length === 0) onOpenPluginSettings(null); else setClaiming(true); }} emptyLabel="暂无账号" />
    {claiming ? <div className="grid gap-3 border-t border-line-soft pt-3">
      {claimError ? <InlineError message={claimError} /> : null}
      {unclaimed.map((account) => <div key={account.id} className="flex items-center justify-between gap-3 text-body-sm">
        <span className="min-w-0 truncate">{account.platform} · {account.displayName || account.platformAccountId} · {accountStatus(account)}</span>
        <button type="button" className={ghostButtonClass} onClick={() => void client.assign(account.id, roleId).then(() => { setClaiming(false); void reload(); }).catch((failure) => setClaimError(String(failure)))}>认领</button>
      </div>)}
      <div className="flex gap-3"><button type="button" className={ghostButtonClass} onClick={() => onOpenPluginSettings(null)}>配置新账号</button><button type="button" className={ghostButtonClass} onClick={() => setClaiming(false)}>取消</button></div>
    </div> : null}
  </div>;
}
