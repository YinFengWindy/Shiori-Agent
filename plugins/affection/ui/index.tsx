import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { ChatAffectionMeter } from "./ChatAffectionMeter";
import { RoleAffectionPanel } from "./RoleAffectionPanel";

/** Affection's role tab and the chat sidebar's thin meter. */
const affectionUiModule: PluginUiModule = {
  pluginId: "affection",
  roleAffection: RoleAffectionPanel,
  chatAffection: ChatAffectionMeter,
};

export default affectionUiModule;
