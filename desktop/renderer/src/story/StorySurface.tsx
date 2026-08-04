import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { cx } from "../shared/styles";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StorySurfaceProps = {
  dataTestId: string;
  panelTestId: string;
  children: ReactNode;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  reducedMotion?: boolean;
  contentClassName?: string;
};

const transition = { duration: 0.28, ease: "easeOut" } as const;
export const STORY_SURFACE_BACKDROP_TRANSITION_SECONDS = 0.7;
export const STORY_SURFACE_BACKDROP_FADE_SECONDS = 0.7;

/** Renders the shared Story backdrop, overlays, panel surface, and entrance motion. */
export function StorySurface({ dataTestId, panelTestId, children, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, reducedMotion = false, contentClassName }: StorySurfaceProps) {
  const systemReducedMotion = useReducedMotion() ?? false;
  const reduceEffects = systemReducedMotion || reducedMotion;

  return (
    <section className={cx("relative h-full min-h-0 overflow-hidden text-[#4A2738]", sharedBackdrop ? "bg-transparent" : "bg-[#1D1520]")} data-testid={dataTestId}>
      {sharedBackdrop ? null : <motion.div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        data-testid={`${dataTestId}-backdrop`}
        initial={{ opacity: 0, scale: reduceEffects ? 1 : 1.06 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: reduceEffects ? 0 : STORY_SURFACE_BACKDROP_TRANSITION_SECONDS, ease: "easeOut" }}
        style={{ backgroundImage: `url(${background.url})` }}
      />}
      <div aria-hidden="true" className="absolute inset-0 bg-[#281421]/42" />
      <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(120deg,rgba(40,20,33,0.2),rgba(40,20,33,0.05)_52%,rgba(104,31,68,0.22))]" />

      <motion.main
        className={cx("relative z-10 flex h-full min-h-0 flex-col", contentClassName || "overflow-y-auto")}
        initial={{ opacity: 0, x: reduceEffects ? 0 : 28 }}
        animate={{ opacity: 1, x: 0 }}
        transition={transition}
      >
        <section className="relative flex min-h-full w-full flex-col border-y border-[#DDA9BE]/75 shadow-[0_18px_48px_rgba(49,17,35,0.3)]" data-testid={panelTestId}>
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-[#FFF8FC]/72 backdrop-blur-xl backdrop-saturate-150"
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
