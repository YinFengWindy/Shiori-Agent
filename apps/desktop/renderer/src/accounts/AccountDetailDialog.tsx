import { Dialog } from "@base-ui/react/dialog";
import { useState } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { accountOnline, type AccountSnapshot } from "@yinfengwindy/shiori-sdk";
import { DialogFrame } from "@yinfengwindy/shiori-sdk/host-internal";
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
    <DialogFrame wide divided closeLabel="关闭账号详情" bodyClassName="pb-1"
      leading={<AccountAvatar avatarUrl={account?.avatarUrl ?? ""} Icon={pluginControls?.Icon} size="lg" />}
      title={account ? accountName(account) : `添加 ${platformLabel} 账号`}
      subtitle={account ? accountChannelLine(platformLabel, account) : null}>
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
    </DialogFrame>
  </Dialog.Root>;
}
