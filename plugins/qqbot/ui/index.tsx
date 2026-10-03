import { RobotIcon } from "@phosphor-icons/react";
import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { QQBotAccountDetail } from "./QQBotAccountDetail";

const qqbotUi: PluginUiModule = {
  pluginId: "qqbot",
  accountDetail: { label: "QQ 官方机器人", icon: RobotIcon, component: QQBotAccountDetail },
};

export default qqbotUi;
