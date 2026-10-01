import React, { useEffect } from "react";
import { ChatCircleIcon } from "@phosphor-icons/react";
import { errorMessage, type PluginAccountDetailComponentProps, type PluginUiModule } from "@shiori/sdk";
import { QQAccountForm } from "./QQAccountForm";
import { useQQAccountForm } from "./useQQAccountForm";

/** One verified account or one temporary login for a new QQ account. */
function QQAccountEditor({ account, roleId, onChanged, client, host }: PluginAccountDetailComponentProps) {
  const form = useQQAccountForm({ accountId: account?.id, roleId, client, onChanged,
    onCleanupError: (failure) => host.feedback.error("QQ 临时连接清理失败", {
      detail: errorMessage(failure, { includeDetail: true }),
    }),
  });
  const accountId = account?.id;
  useEffect(() => {
    if (accountId || !form.ref) return;
    const ref = form.ref;
    return () => { void client.call("accounts.cancel", { ref, role_id: roleId }).catch((failure: unknown) => {
      host.feedback.error("QQ 临时连接清理失败", { detail: errorMessage(failure, { includeDetail: true }) });
    }); };
  }, [accountId, form.ref, client, roleId, host.feedback]);
  return <QQAccountForm account={account} host={host} form={form} />;
}

/** QQ's controls in the role page's account detail. */
export function QQAccountDetail(props: PluginAccountDetailComponentProps) {
  return <QQAccountEditor {...props} />;
}

const qqUiModule: PluginUiModule = {
  pluginId: "qq",
  accountDetail: { label: "QQ", icon: ChatCircleIcon, component: QQAccountDetail },
};
export default qqUiModule;
