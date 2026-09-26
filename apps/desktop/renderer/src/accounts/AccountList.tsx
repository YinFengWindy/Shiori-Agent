import { Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import { AccountDetailDialog } from "./AccountDetailDialog";
import type { AccountSnapshot } from "./accountClient";
import { accountStatus } from "./accountPresentation";

/** Reusable identity list; new-account navigation is supplied by its owner. */
export function AccountList({ title, accounts, error, onRefresh, onAdd, emptyLabel, showOwner = false }: {
  title: string;
  accounts: AccountSnapshot[] | null;
  error: string;
  onRefresh: () => void;
  onAdd?: () => void;
  emptyLabel: string;
  showOwner?: boolean;
}) {
  const [selected, setSelected] = useState<AccountSnapshot | null>(null);
  return <section className="grid gap-3" aria-label={title}>
    <div className="flex items-center justify-between gap-3">
      <h3 className="m-0 text-body font-semibold text-ink">{title}</h3>
      {onAdd ? <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={onAdd}><Plus className="h-4 w-4" />添加账号</button> : null}
    </div>
    {error ? <InlineError message={error} /> : null}
    {accounts?.length === 0 ? <p className="m-0 text-body-sm text-ink-muted">{emptyLabel}</p> : null}
    {accounts?.map((account) => <button key={account.id} type="button" className="flex w-full items-center justify-between gap-3 border-b border-line-soft py-3 text-left last:border-b-0 hover:text-accent-text" onClick={() => setSelected(account)}>
      <span className="grid min-w-0 gap-0.5"><span className="truncate text-body font-medium text-ink">{account.platform} · {account.displayName || account.platformAccountId}</span><span className="truncate text-body-sm text-ink-muted">{account.platformAccountId}</span></span>
      <span className="grid shrink-0 gap-0.5 text-right text-body-sm text-ink-secondary">
        <span>{accountStatus(account)}</span>
        {showOwner ? <span className="text-ink-muted">{account.roleId ?? "未分配"}</span> : null}
      </span>
    </button>)}
    {selected ? <AccountDetailDialog key={selected.id} account={accounts?.find((item) => item.id === selected.id) ?? selected} pluginId={selected.pluginId} onClose={() => setSelected(null)} onChanged={onRefresh} /> : null}
  </section>;
}
