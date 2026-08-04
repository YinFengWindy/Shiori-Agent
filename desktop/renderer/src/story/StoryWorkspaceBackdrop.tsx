import { motion, useReducedMotion } from "motion/react";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryWorkspaceBackdropProps = {
  background: StoryMenuBackground;
  blur?: StoryWorkspaceBackdropBlur;
};

/** Selects the blur strength for the current Story presentation surface. */
export type StoryWorkspaceBackdropBlur = "none" | "surface" | "archive";

/** Duration of the shared Story workspace blur transition. */
export const STORY_WORKSPACE_BACKDROP_TRANSITION_SECONDS = 0.7;

const backdropFilters: Record<StoryWorkspaceBackdropBlur, string> = {
  none: "blur(0px) saturate(1)",
  surface: "blur(24px) saturate(1.5)",
  archive: "blur(4px) saturate(1)",
};

/** Keeps one Story background mounted while the workspace changes presentation modes. */
export function StoryWorkspaceBackdrop({ background, blur = "none" }: StoryWorkspaceBackdropProps) {
  const reducedMotion = useReducedMotion() ?? false;
  const targetFilter = backdropFilters[blur];
  const shouldBlur = blur !== "none";

  return <>
    <motion.div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 bg-[#1D1520] bg-cover bg-center bg-no-repeat"
      data-testid="story-workspace-backdrop"
      initial={reducedMotion ? false : { opacity: 0, scale: 1.06 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: reducedMotion ? 0 : 1.4, ease: "easeOut" }}
      style={{ backgroundImage: `url(${background.url})` }}
    />
    <motion.div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0"
      data-blur-mode={blur}
      data-testid="story-workspace-backdrop-blur"
      initial={shouldBlur && !reducedMotion ? { opacity: 0, backdropFilter: backdropFilters.none } : false}
      animate={{ opacity: shouldBlur ? 1 : 0, backdropFilter: targetFilter }}
      transition={{ duration: reducedMotion ? 0 : STORY_WORKSPACE_BACKDROP_TRANSITION_SECONDS, ease: "easeOut" }}
    />
  </>;
}
