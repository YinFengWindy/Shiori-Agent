import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { naturalChatRoleSettings } from "./roleSettings";

const naturalChatUiModule: PluginUiModule = {
  pluginId: "natural_chat",
  roleSettings: naturalChatRoleSettings,
};

export default naturalChatUiModule;
