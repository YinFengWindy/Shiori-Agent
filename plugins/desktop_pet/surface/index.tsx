import type { PluginSurfaceModule } from "@shiori/plugin-sdk";
import { DesktopPetSurface } from "./DesktopPetSurface";
// Imported here rather than from the component so the component stays loadable
// by the plain node:test runner, which has no CSS loader. Vite pulls this into
// the shared `surface.html` bundle through the entry below.
import "./styles.css";

/**
 * The desktop pet's `desktop.surface` contribution.
 *
 * Compiled into the host's shared `surface.html` bundle by the build-time glob
 * in `apps/desktop/renderer/src/surface/pluginSurfaceModules.ts`, and mounted
 * by `SurfaceRoot` for whichever window carries `?plugin=desktop_pet`. The
 * host holds no pet-specific renderer entry any more: `pet.html` is gone.
 */
export default {
  pluginId: "desktop_pet",
  surface: { component: DesktopPetSurface },
} satisfies PluginSurfaceModule;
