import { motion, useReducedMotion } from "motion/react";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryWorkspaceBackdropProps = {
  background: StoryMenuBackground;
};

/** Keeps one Story background mounted while the workspace changes presentation modes. */
export function StoryWorkspaceBackdrop({ background }: StoryWorkspaceBackdropProps) {
  const reducedMotion = useReducedMotion() ?? false;

  return <motion.div
    aria-hidden="true"
    className="pointer-events-none absolute inset-0 bg-[#1D1520] bg-cover bg-center bg-no-repeat"
    data-testid="story-workspace-backdrop"
    initial={reducedMotion ? false : { opacity: 0, scale: 1.06 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ duration: reducedMotion ? 0 : 1.4, ease: "easeOut" }}
    style={{ backgroundImage: `url(${background.url})` }}
  />;
}
