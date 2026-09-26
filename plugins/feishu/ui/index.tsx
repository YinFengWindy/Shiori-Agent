import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { FeishuAccountDetail } from "./FeishuAccountDetail";

/** The host provides the account list; this module owns only platform controls. */
const feishuUiModule: PluginUiModule = {
  pluginId: "feishu",
  settingsSection: { kind: "component", label: "飞书", component: () => null },
  accountDetail: { component: FeishuAccountDetail },
};

export default feishuUiModule;
