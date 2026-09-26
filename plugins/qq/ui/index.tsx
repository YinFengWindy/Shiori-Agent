import React from "react";
import type { PluginAccountDetailComponentProps, PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { QQAccountForm } from "./QQAccountForm";
import { QQDraftsSection } from "./QQDraftsSection";
import { useQQAccountForm } from "./useQQAccountForm";

/** Binds QQ's connection form to the shared host account detail slot. */
export function QQAccountDetail({ account, onChanged, client, host, draftRef = "" }: PluginAccountDetailComponentProps & { draftRef?: string }) {
  const form = useQQAccountForm({ accountId: account?.id, draftRef, client, onChanged });
  return <QQAccountForm account={account} host={host} form={form} />;
}

const qqUiModule: PluginUiModule = {
  pluginId: "qq",
  // The host appends PluginAccountsSection; keep the legacy schema available
  // for migration while hiding its old autosave form.
  settingsSection: { kind: "component", label: "QQ", component: (props) => <QQDraftsSection {...props} Editor={QQAccountDetail} /> },
  accountDetail: { component: QQAccountDetail },
};
export default qqUiModule;
