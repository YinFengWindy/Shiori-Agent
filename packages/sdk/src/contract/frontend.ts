import type { PluginUiModule } from "./uiModule";
import type { PluginBackgroundContribution } from "./background";
import type { PluginSurfaceModule } from "./surfaceModule";

/** Named exports of one plugin frontend entry, evaluated without starting effects. */
export type PluginFrontendModule = {
  ui?: PluginUiModule;
  background?: PluginBackgroundContribution;
  surface?: PluginSurfaceModule;
};
