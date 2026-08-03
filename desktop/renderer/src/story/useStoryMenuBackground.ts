import { useEffect, useState } from "react";
import type { RoleRecord } from "../shared/types";
import { toFileUrl } from "../shared/format";
import { STORY_MENU_BACKGROUND_URL } from "./storyStaticAssets";
import {
  chooseRandomStoryMenuAsset,
  collectStoryMenuAssetCandidates,
  loadLandscapeStoryMenuAssets,
  type StoryMenuAssetUrlResolver,
  type StoryMenuImageFactory,
} from "./storyMenuBackground";

/** Injectable dependencies for deterministic Story menu background resolution. */
export type StoryMenuBackgroundResolverDependencies = {
  resolveAssetUrl?: StoryMenuAssetUrlResolver;
  createImage?: StoryMenuImageFactory;
  random?: () => number;
};

/** Resolves one random landscape role illustration or the bundled horizontal fallback. */
export async function resolveStoryMenuBackground(
  roles: readonly Pick<RoleRecord, "id" | "illustrations_abs">[],
  dependencies: StoryMenuBackgroundResolverDependencies = {},
): Promise<string> {
  const candidates = collectStoryMenuAssetCandidates(roles, dependencies.resolveAssetUrl ?? toFileUrl);
  if (!candidates.length) return STORY_MENU_BACKGROUND_URL;
  const landscapeAssets = await loadLandscapeStoryMenuAssets(
    candidates,
    dependencies.createImage ?? (() => new Image()),
  );
  return chooseRandomStoryMenuAsset(landscapeAssets, dependencies.random)?.assetUrl ?? STORY_MENU_BACKGROUND_URL;
}

/** Keeps one randomized Story menu backdrop per launcher mount and ignores stale probes on unmount. */
export function useStoryMenuBackground(roles: readonly RoleRecord[]): string {
  const [backgroundUrl, setBackgroundUrl] = useState(STORY_MENU_BACKGROUND_URL);

  useEffect(() => {
    let mounted = true;
    void resolveStoryMenuBackground(roles).then((nextBackgroundUrl) => {
      if (mounted) setBackgroundUrl(nextBackgroundUrl);
    });
    return () => {
      mounted = false;
    };
  }, [roles]);

  return backgroundUrl;
}
