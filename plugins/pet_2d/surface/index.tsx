import type { PluginSurfaceModule } from "@yinfengwindy/shiori-sdk";
import { AvatarSurface } from "./AvatarSurface";
import "@yinfengwindy/shiori-pet/styles.css";
/** The provider's transparent model surface. */
export default { pluginId: "pet_2d", surface: { component: AvatarSurface } } satisfies PluginSurfaceModule;
