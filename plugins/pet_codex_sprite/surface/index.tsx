import type { PluginSurfaceModule } from "@yinfengwindy/shiori-sdk";
import { SpriteSurface } from "./SpriteSurface";
import "@yinfengwindy/shiori-pet/styles.css";
/** Only the sprite provider loads the sprite surface renderer. */
export default { pluginId: "pet_codex_sprite", surface: { component: SpriteSurface } } satisfies PluginSurfaceModule;
