import { Dialog } from "@base-ui/react/dialog";
import { XIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { iconButtonClass, accountOnline, type AccountSnapshot } from "@shiori/sdk";
import { dialogBackdropClass } from "../shared/styles";
import { Reveal } from "../shared/ui/Reveal";
import { accountChannelLabel, accountChannelLine, accountName } from "./accountPresentation";
import { AccountAvatar } from "./AccountAvatar";
import { AccountDangerZone } from "./AccountDangerZone";
import { AccountDetailActionsTarget } from "./AccountDetailActions";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";

/**
 * One role's account detail, top to bottom: who it is, the platform's own
 * connection controls (account.detail, led by the shared status card), the
 * response rules while the account is online, then the danger zone. A null
 * account is a new one being added for `roleId`.
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
  const platformLabel = accountChannelLabel(pluginId, pluginControls);
  // The danger zone's action row, where plugin secondary actions are portaled.
  const [actionsTarget, setActionsTarget] = useState<HTMLElement | null>(null);

  return <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className={dialogBackdropClass} />
      <Dialog.Popup className="confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[min(42rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-md border border-line bg-surface p-6 shadow-panel">
        <div className="flex items-center justify-between gap-3 border-b border-line-soft pb-4">
          <div className="flex min-w-0 items-center gap-3">
            <AccountAvatar avatarUrl={account?.avatarUrl ?? ""} Icon={pluginControls?.Icon} size="lg" />
            <div className="grid min-w-0 gap-0.5">
              <Dialog.Title className="truncate font-display text-title font-semibold text-ink">
                {account ? accountName(account) : `添加 ${platformLabel} 账号`}
              </Dialog.Title>
              {account ? <p className="m-0 truncate text-body-sm text-ink-muted">{accountChannelLine(platformLabel, account)}</p> : null}
            </div>
          </div>
          <Dialog.Close className={iconButtonClass} aria-label="关闭账号详情"><XIcon className="h-5 w-5" /></Dialog.Close>
        </div>
        <div className="scrollbar-stable min-h-0 overflow-y-auto pb-1 pt-5">
          {PlatformControls ? <section aria-label="平台设置">
            <AccountDetailActionsTarget value={actionsTarget}>
              <PlatformControls account={account} roleId={roleId} onChanged={onChanged} />
            </AccountDetailActionsTarget>
          </section> : null}
          {/* Rules only matter while the account can receive messages. */}
          <Reveal show={accountOnline(account)} className="pt-6">
            {account ? <AccountResponseRulesEditor key={account.id} account={account} onChanged={onChanged} /> : null}
          </Reveal>
          <Reveal show={Boolean(account)} className="pt-6">
            {account ? <AccountDangerZone account={account} roleId={roleId} onChanged={onChanged}
              onDeleted={onClose} onActionsTarget={setActionsTarget} /> : null}
          </Reveal>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
