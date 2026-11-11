import type { PluginSurfaceModule } from "@yinfengwindy/shiori-sdk";
import { AvatarSurface } from "./AvatarSurface";
import "@shiori-plugin/desktop_pet/provider/styles.css";
/** The provider's transparent model surface. */
export default { pluginId: "pet_2d", surface: { component: AvatarSurface } } satisfies PluginSurfaceModule;
