import type React from "react";
import { MotionConfig } from "motion/react";
import { useStoryPreferences } from "./storyPreferences";

type StoryAppSurfaceProps = {
  children: React.ReactNode;
};

/**
 * Top-level Story application surface, deliberately separate from the desktop
 * chat shell. `story-root` scopes the Story tokens from story.css;
 * `scrollbar-native` keeps the platform scrollbar here because Story sits
 * outside the host restyle. The Story "reduce motion" preference applies to
 * every motion animation below it, on top of the system setting.
 */
export function StoryAppSurface({ children }: StoryAppSurfaceProps) {
  const { reducedMotion } = useStoryPreferences();
  return (
    <MotionConfig reducedMotion={reducedMotion ? "always" : "user"}>
      <section className="story-root scrollbar-native h-screen min-h-0 overflow-hidden text-[color:var(--story-ink)]" data-reduced-motion={reducedMotion} data-testid="story-app-surface">
        {children}
      </section>
    </MotionConfig>
  );
}
