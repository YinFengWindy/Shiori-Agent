import { TelegramLogoIcon } from "@phosphor-icons/react";
import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { TelegramAccountDetail } from "./TelegramAccountDetail";

/** Telegram Bots are added and managed only from a role's account page. */
const telegramUi: PluginUiModule = {
  pluginId: "telegram",
  accountDetail: { label: "Telegram", icon: TelegramLogoIcon, component: TelegramAccountDetail },
};

export default telegramUi;
