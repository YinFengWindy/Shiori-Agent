import { PlusIcon, PuzzlePieceIcon, TrashIcon } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { compactButtonSizeClass, cx, dangerGhostButtonSurfaceClass, ghostButtonSurfaceClass } from "../shared/styles";
import type { AccountDetailEntry } from "../plugins/pluginUiRegistry";
import type { AccountSnapshot } from "./accountClient";
import { accountName, accountStatus } from "./accountPresentation";

const connectionTones = {
  online: "bg-success-soft text-success-text",
  connecting: "bg-warning-soft text-warning-text",
  login_required: "bg-accent-soft text-accent-text",
  error: "bg-danger-soft text-danger-text",
  offline: "bg-surface-soft text-ink-muted",
  unknown: "bg-surface-soft text-ink-muted",
} as const;

/** One row per enabled channel, whether this role has an account there yet or not. */
export function AccountList({ platforms, accounts, error, onRefresh, onOpen, onDelete }: {
  platforms: AccountDetailEntry[];
  accounts: AccountSnapshot[] | null;
  error: string;
  onRefresh: () => void;
  onOpen: (pluginId: string, accountId: string | null) => void;
  onDelete: (account: AccountSnapshot) => void;
}) {
  return <section className="grid gap-3" aria-label="账号">
    <h3 className="m-0 text-body font-semibold text-ink">账号</h3>
    {error ? <InlineError message={error} actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={onRefresh}>重试</button>} /> : null}
    {platforms.length === 0 ? <p className="m-0 text-body-sm text-ink-muted">暂无可用渠道</p> : null}
    <div className="grid divide-y divide-line-soft">
      {platforms.map(({ pluginId, label, Icon }) => {
        const account = accounts?.find((item) => item.pluginId === pluginId);
        return <div key={pluginId} className="flex min-w-0 items-center gap-3 py-3 first:pt-0 last:pb-0">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-surface-soft text-ink-secondary" aria-hidden="true">
            {Icon ? <Icon className="h-5 w-5" /> : <PuzzlePieceIcon className="h-5 w-5" />}
          </span>
          <span className="grid min-w-0 flex-1 gap-0.5">
            <span className="flex flex-wrap items-center gap-2 text-body font-medium text-ink">{label}
              {account ? <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-caption font-medium", connectionTones[account.runtimeActive ? account.connection : "offline"])}>{accountStatus(account)}</span> : null}
            </span>
            {account ? <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 text-body-sm">
              <span className="truncate text-ink-secondary">{accountName(account)}</span>
              {account.displayName && account.displayName !== account.platformAccountId ? <span className="truncate text-ink-muted">{account.platformAccountId}</span> : null}
            </span> : <span className="text-body-sm text-ink-muted">{accounts ? "未添加" : error ? "读取失败" : "读取中"}</span>}
          </span>
          <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)}
            disabled={!accounts || Boolean(error)} onClick={() => onOpen(pluginId, account?.id ?? null)}>
            {account ? "查看" : <><PlusIcon className="h-4 w-4" />添加</>}
          </button>
          {account ? <button type="button" className={cx(dangerGhostButtonSurfaceClass, compactButtonSizeClass)}
            aria-label={`删除 ${accountName(account)}`} title={`删除 ${accountName(account)}`}
            onClick={() => onDelete(account)}><TrashIcon className="h-4 w-4" /></button> : null}
        </div>;
      })}
    </div>
  </section>;
}
