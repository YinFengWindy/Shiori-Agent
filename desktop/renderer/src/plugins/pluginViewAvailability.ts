import type { AppMainView } from "../shared/types";
import type { PluginCatalog } from "./pluginCatalog";

const requiredRendererByView: Partial<Record<AppMainView["kind"], string>> = {
  "image-studio": "novelai.image-studio",
  "image-prompt-tags": "novelai.prompt-tags",
};

/** Returns whether a route owned by a plugin is available in the loaded catalog. */
export function isPluginViewAvailable(viewKind: AppMainView["kind"], catalog: PluginCatalog) {
  const renderer = requiredRendererByView[viewKind];
  return !renderer || catalog.hasRenderer(renderer);
}

/** Decides when an online app must recover an unavailable plugin deep link. */
export function shouldFallbackFromPluginView(
  bridgeState: string,
  viewKind: AppMainView["kind"],
  catalog: PluginCatalog,
) {
  return bridgeState === "online" && !isPluginViewAvailable(viewKind, catalog);
}
