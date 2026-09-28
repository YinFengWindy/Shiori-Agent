import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { QQBotAccountDetail } from "./QQBotAccountDetail";

const qqbotUi: PluginUiModule = {
  pluginId: "qqbot",
  accountDetail: { label: "QQ 官方机器人", component: QQBotAccountDetail },
};

export default qqbotUi;
