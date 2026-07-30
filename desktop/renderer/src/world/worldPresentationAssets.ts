import { unavailableLocalAssetUrl } from "../../../src/shared";
import { toFileUrl, type LocalAssetUrlResolver } from "../shared/format";
import type { PerformancePlan } from "./presentationProtocol";

function hydrateValue(value: unknown, resolveLocalAssetUrl: LocalAssetUrlResolver): unknown {
  if (Array.isArray(value)) return value.map((item) => hydrateValue(item, resolveLocalAssetUrl));
  if (typeof value !== "object" || value === null) return value;

  const source = value as Record<string, unknown>;
  const hydrated = Object.fromEntries(
    Object.entries(source)
      .filter(([key]) => key !== "image_path")
      .map(([key, item]) => [key, hydrateValue(item, resolveLocalAssetUrl)]),
  );
  if (typeof source.image_path === "string") {
    const imageUrl = resolveLocalAssetUrl(source.image_path);
    if (imageUrl !== unavailableLocalAssetUrl && typeof hydrated.imageUrl !== "string") {
      hydrated.imageUrl = imageUrl;
    }
  }
  return hydrated;
}

/** Replaces trusted bridge paths with opaque local URLs before Pixi sees a plan. */
export function hydrateWorldPresentationAssets(
  plan: PerformancePlan,
  resolveLocalAssetUrl?: LocalAssetUrlResolver,
): PerformancePlan {
  const resolver = resolveLocalAssetUrl ?? toFileUrl;
  return {
    ...plan,
    cues: plan.cues.map((cue) => ({
      ...cue,
      payload: hydrateValue(cue.payload, resolver) as Record<string, unknown>,
    })),
  };
}
