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
import {
  DEFAULT_STORY_MENU_THEME,
  resolveStoryMenuTheme,
  type StoryMenuTheme,
} from "./storyMenuTheme";

/** Injectable dependencies for deterministic Story menu background resolution. */
export type StoryMenuBackgroundResolverDependencies = {
  resolveAssetUrl?: StoryMenuAssetUrlResolver;
  createImage?: StoryMenuImageFactory;
  random?: () => number;
};

/** One resolved Story launcher backdrop and the theme derived from its pixels. */
export type StoryMenuBackground = {
  url: string;
  theme: StoryMenuTheme;
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
export function useStoryMenuBackground(roles: readonly RoleRecord[]): StoryMenuBackground {
  const [background, setBackground] = useState<StoryMenuBackground>({
    url: STORY_MENU_BACKGROUND_URL,
    theme: DEFAULT_STORY_MENU_THEME,
  });

  useEffect(() => {
    let mounted = true;
    void resolveStoryMenuBackground(roles).then(async (nextBackgroundUrl) => {
      const theme = nextBackgroundUrl === STORY_MENU_BACKGROUND_URL
        ? DEFAULT_STORY_MENU_THEME
        : await resolveStoryMenuTheme(nextBackgroundUrl);
      if (mounted) setBackground({ url: nextBackgroundUrl, theme });
    });
    return () => {
      mounted = false;
    };
  }, [roles]);

  return background;
}
