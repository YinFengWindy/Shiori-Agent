import type { PluginSurfaceModule } from "@yinfengwindy/shiori-sdk";
import { SpriteSurface } from "./SpriteSurface";
import "@shiori-plugin/desktop_pet/provider/styles.css";
/** Only the sprite provider loads the sprite surface renderer. */
export default { pluginId: "pet_codex_sprite", surface: { component: SpriteSurface } } satisfies PluginSurfaceModule;
