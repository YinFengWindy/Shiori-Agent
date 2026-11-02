import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { proactiveRoleSettings } from "./roleSettings";

/** The proactive plugin contributes its existing role settings card. */
const proactiveUiModule: PluginUiModule = { pluginId: "proactive", roleSettings: proactiveRoleSettings };
export default proactiveUiModule;
