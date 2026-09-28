import { Dialog } from "@base-ui/react/dialog";
import { XIcon } from "@phosphor-icons/react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { InlineError } from "../shared/feedback/InlineError";
import { iconButtonClass } from "../shared/styles";
import { accountName } from "./accountPresentation";
import type { AccountSnapshot } from "./accountClient";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";
import { AccountStatusDot } from "./AccountStatusDot";

/**
 * One role's account detail: status, the platform's own connection controls
 * (account.detail), then response rules. A null account is a new one being
 * added for `roleId`.
 */
export function AccountDetailDialog({ account, pluginId, roleId, onClose, onChanged }: {
  account: AccountSnapshot | null;
  pluginId: string;
  roleId: string;
  onClose: () => void;
  onChanged: (accountId?: string) => void;
}) {
  const isPluginEnabled = usePluginEnabledState();
  const pluginControls = pluginUiRegistry.getAccountDetail(pluginId, isPluginEnabled);
  const PlatformControls = pluginControls?.Component;
  const platformLabel = pluginControls?.label ?? account?.platform;

  return <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
      <Dialog.Popup className="confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[min(42rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-md border border-line bg-surface p-6 shadow-panel">
        <div className={`flex items-start justify-between gap-3 ${account ? "border-b border-line-soft pb-4" : ""}`}>
          <div className="min-w-0">
            <Dialog.Title className="font-display text-title font-semibold text-ink">{account ? accountName(account) : pluginControls ? `添加 ${pluginControls.label} 账号` : "添加账号"}</Dialog.Title>
            {account ? <p className="m-0 flex flex-wrap items-center gap-x-2 break-all text-body-sm text-ink-muted">
              <AccountStatusDot account={account} withText />
              <span>{platformLabel} · {account.platformAccountId}</span>
            </p> : null}
          </div>
          <Dialog.Close className={iconButtonClass} aria-label="关闭账号详情"><XIcon className="h-5 w-5" /></Dialog.Close>
        </div>
        <div className="scrollbar-stable grid min-h-0 gap-6 overflow-y-auto py-5">
          {account?.error && account.connection === "error" ? <InlineError message={account.error} /> : null}
          {/* Connection comes first; response rules only exist once the account does. */}
          {PlatformControls ? <section aria-label="平台设置">
            <PlatformControls account={account} roleId={roleId} onChanged={onChanged} />
          </section> : null}
          {account ? <div className={PlatformControls ? "border-t border-line-soft pt-5" : ""}>
            <AccountResponseRulesEditor account={account} onChanged={onChanged} />
          </div> : null}
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
