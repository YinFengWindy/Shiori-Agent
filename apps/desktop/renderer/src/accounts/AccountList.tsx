import { CaretRightIcon, PlusIcon } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactGhostButtonClass, cx, sidebarNavItemClass, type AccountSnapshot } from "@shiori/sdk";
import type { AccountDetailEntry } from "../plugins/pluginUiRegistry";
import { accountStatusView } from "@shiori/sdk/host-internal";
import { accountChannelLine, accountName } from "./accountPresentation";
import { AccountAvatar } from "./AccountAvatar";
import { AccountStatusDot } from "./AccountStatusDot";

const rowClass = cx(
  sidebarNavItemClass,
  "flex w-full min-w-0 cursor-pointer items-center gap-3 px-2 py-2.5 text-left disabled:cursor-default disabled:opacity-60 disabled:hover:bg-transparent",
);

/**
 * One whole-row button per enabled channel, whether this role has an account
 * there yet or not; either way the row opens that channel's account detail.
 */
export function AccountList({ platforms, accounts, error, onRefresh, onOpen }: {
  platforms: AccountDetailEntry[];
  accounts: AccountSnapshot[] | null;
  error: string;
  onRefresh: () => void;
  onOpen: (pluginId: string, accountId: string | null) => void;
}) {
  return <section className="grid gap-3" aria-label="账号">
    <h3 className="m-0 text-body font-semibold text-ink">账号</h3>
    {error ? <InlineError message={error} actions={<button type="button" className={compactGhostButtonClass} onClick={onRefresh}>重试</button>} /> : null}
    {platforms.length === 0 ? <p className="m-0 text-body-sm text-ink-muted">暂无可用渠道</p> : null}
    <div className="-mx-2 grid gap-0.5">
      {platforms.map(({ pluginId, label, Icon }) => {
        const account = accounts?.find((item) => item.pluginId === pluginId);
        const status = account ? accountStatusView(account) : null;
        return <button key={pluginId} type="button" className={rowClass}
          disabled={!accounts || Boolean(error)} onClick={() => onOpen(pluginId, account?.id ?? null)}
          aria-label={account && status
            ? `${accountName(account)}，${status.label}，${accountChannelLine(label, account)}`
            : `添加 ${label} 账号`}>
          <AccountAvatar avatarUrl={account?.avatarUrl ?? ""} Icon={Icon} />
          <span className="grid min-w-0 flex-1 gap-0.5">
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-body font-medium text-ink">{account ? accountName(account) : label}</span>
              {status ? <AccountStatusDot status={status} /> : null}
            </span>
            <span className="truncate text-body-sm text-ink-muted">
              {account ? accountChannelLine(label, account) : accounts ? "未添加" : error ? "读取失败" : "读取中"}
            </span>
          </span>
          {account
            ? <CaretRightIcon className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
            : <PlusIcon className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />}
        </button>;
      })}
    </div>
  </section>;
}
