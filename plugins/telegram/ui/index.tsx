import type { PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { TelegramAccountDetail } from "./TelegramAccountDetail";

/** Telegram account settings use the host's shared account dialog. */
const telegramUi: PluginUiModule = {
  pluginId: "telegram",
  // The host supplies PluginAccountsSection for this settings entry.
  settingsSection: { kind: "component", label: "Telegram", component: () => null },
  accountDetail: { component: TelegramAccountDetail },
};

export default telegramUi;
