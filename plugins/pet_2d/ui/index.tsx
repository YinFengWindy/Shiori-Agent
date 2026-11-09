import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { FaceCaptureSettings } from "./FaceCaptureSettings";
import { avatarRoleSettings } from "./roleSettings";
/** The 2.5D plugin's local camera preferences and explicit capture switch. */
export default { pluginId: "pet_2d", roleSettings: avatarRoleSettings, settingsSection: { kind: "component", label: "2.5D 形象", component: FaceCaptureSettings } } satisfies PluginUiModule;
