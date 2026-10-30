import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { ChatAffectionStatus } from "./ChatAffectionStatus";
import { RoleAffectionPanel } from "./RoleAffectionPanel";

/** Affection's role tab and its block in the chat status sidebar. */
const affectionUiModule: PluginUiModule = {
  pluginId: "affection",
  roleAffection: RoleAffectionPanel,
  chatAffection: ChatAffectionStatus,
};

export default affectionUiModule;
