import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cx } from "@yinfengwindy/shiori-sdk";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import { useStoryReducedMotion } from "./storyPreferences";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StorySurfaceProps = {
  dataTestId: string;
  panelTestId: string;
  children: ReactNode;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  contentClassName?: string;
};

const transition = { duration: 0.28, ease: "easeOut" } as const;

/** Duration of the standalone Story surface backdrop entrance animation. */
export const STORY_SURFACE_BACKDROP_TRANSITION_SECONDS = 0.7;

/** Duration of the shared-backdrop fade used by Story surfaces. */
export const STORY_SURFACE_BACKDROP_FADE_SECONDS = 0.7;

/** Renders the shared Story backdrop, overlays, panel surface, and entrance motion. */
export function StorySurface({ dataTestId, panelTestId, children, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, contentClassName }: StorySurfaceProps) {
  const reduceEffects = useStoryReducedMotion();

  return (
    <section className={cx("relative h-full min-h-0 overflow-hidden text-[color:var(--story-ink)]", sharedBackdrop ? "bg-transparent" : "bg-[color:var(--story-night)]")} data-testid={dataTestId}>
      {sharedBackdrop ? null : <motion.div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        data-testid={`${dataTestId}-backdrop`}
        initial={{ opacity: 0, scale: reduceEffects ? 1 : 1.06 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: reduceEffects ? 0 : STORY_SURFACE_BACKDROP_TRANSITION_SECONDS, ease: "easeOut" }}
        style={{ backgroundImage: `url(${background.url})` }}
      />}
      <div aria-hidden="true" className="absolute inset-0 bg-[color:var(--story-veil)]" />

      <motion.main
        className={cx("relative z-10 flex h-full min-h-0 flex-col", contentClassName || "overflow-y-auto")}
        initial={{ opacity: 0, x: reduceEffects ? 0 : 28 }}
        animate={{ opacity: 1, x: 0 }}
        transition={transition}
      >
        <section className="relative flex min-h-full w-full flex-col border-y border-[color:var(--story-line)] shadow-[var(--story-shadow-panel)]" data-testid={panelTestId}>
          <motion.div
            aria-hidden="true"
            className={cx("pointer-events-none absolute inset-0 bg-[color:var(--story-paper)]", !sharedBackdrop && "backdrop-blur-xl backdrop-saturate-150")}
            initial={sharedBackdrop && !reduceEffects ? { opacity: 0 } : false}
            animate={sharedBackdrop && !reduceEffects ? { opacity: 1 } : undefined}
            transition={{ duration: sharedBackdrop && !reduceEffects ? STORY_SURFACE_BACKDROP_FADE_SECONDS : 0, ease: "easeOut" }}
          />
          <div className="relative z-10 flex min-h-full w-full flex-col">{children}</div>
        </section>
      </motion.main>
    </section>
  );
}
