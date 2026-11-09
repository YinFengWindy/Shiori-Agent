import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { FaceCaptureSettings } from "./FaceCaptureSettings";
/** The 2.5D plugin's local camera preferences and explicit capture switch. */
export default { pluginId: "pet_2d", settingsSection: { kind: "component", label: "2.5D 形象", component: FaceCaptureSettings } } satisfies PluginUiModule;
