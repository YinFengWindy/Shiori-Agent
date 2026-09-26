import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { QQBotAccountDetail } from "./QQBotAccountDetail";

const qqbotUi: PluginUiModule = {
  pluginId: "qqbot",
  accountDetail: { component: QQBotAccountDetail },
};

export default qqbotUi;
