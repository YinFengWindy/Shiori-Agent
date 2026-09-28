import React from "react";
import type { PluginAccountDetailComponentProps, PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { QQAccountForm } from "./QQAccountForm";
import { QQDraftsSection } from "./QQDraftsSection";
import { useQQAccountForm } from "./useQQAccountForm";

/** One QQ connection form: a saved account, a selected draft, or a new draft for `roleId`. */
function QQAccountEditor({ account, roleId, onChanged, client, host, draftRef = "" }: PluginAccountDetailComponentProps & { draftRef?: string }) {
  const form = useQQAccountForm({ accountId: account?.id, draftRef, roleId, client, onChanged });
  return <QQAccountForm account={account} host={host} form={form} />;
}

/** QQ's controls in the role page's account detail; adding one starts from the role's drafts. */
export function QQAccountDetail(props: PluginAccountDetailComponentProps) {
  if (props.account) return <QQAccountEditor {...props} />;
  return <QQDraftsSection roleId={props.roleId} client={props.client} host={props.host}
    onChanged={props.onChanged} Editor={QQAccountEditor} />;
}

const qqUiModule: PluginUiModule = {
  pluginId: "qq",
  accountDetail: { label: "QQ", component: QQAccountDetail },
};
export default qqUiModule;
