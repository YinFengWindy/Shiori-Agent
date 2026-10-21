import { ChatCircleDotsIcon } from "@phosphor-icons/react";
import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { GrokAccountDetail } from "./GrokAccountDetail";

/** Each role owns one independent connection to an existing Grok Bot. */
const grokUiModule: PluginUiModule = {
  pluginId: "grok_bot",
  accountDetail: { label: "Grok Bot", icon: ChatCircleDotsIcon, component: GrokAccountDetail },
};
export default grokUiModule;
