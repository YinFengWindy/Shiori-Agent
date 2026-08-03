import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { cx } from "../shared/styles";
import { STORY_MENU_BACKGROUND_URL } from "./storyStaticAssets";

type StorySurfaceProps = {
  dataTestId: string;
  panelTestId: string;
  children: ReactNode;
  reducedMotion?: boolean;
  contentClassName?: string;
};

const transition = { duration: 0.28, ease: "easeOut" } as const;

/** Renders the shared Story backdrop, overlays, panel surface, and entrance motion. */
export function StorySurface({ dataTestId, panelTestId, children, reducedMotion = false, contentClassName }: StorySurfaceProps) {
  const systemReducedMotion = useReducedMotion() ?? false;
  const reduceEffects = systemReducedMotion || reducedMotion;

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#1D1520] text-[#4A2738]" data-testid={dataTestId}>
      <motion.div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        data-testid={`${dataTestId}-backdrop`}
        initial={{ opacity: 0, scale: reduceEffects ? 1 : 1.06 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: reduceEffects ? 0 : 1.4, ease: "easeOut" }}
        style={{ backgroundImage: `url(${STORY_MENU_BACKGROUND_URL})` }}
      />
      <div aria-hidden="true" className="absolute inset-0 bg-[#281421]/42" />
      <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(120deg,rgba(40,20,33,0.2),rgba(40,20,33,0.05)_52%,rgba(104,31,68,0.22))]" />

      <motion.main
        className={cx("relative z-10 flex h-full min-h-0 flex-col", contentClassName || "overflow-y-auto")}
        initial={{ opacity: 0, x: reduceEffects ? 0 : 28 }}
        animate={{ opacity: 1, x: 0 }}
        transition={transition}
      >
        <section className="flex min-h-full w-full flex-col border-y border-[#DDA9BE]/75 bg-[#FFF8FC]/90 shadow-[0_18px_48px_rgba(49,17,35,0.3)] backdrop-blur-md" data-testid={panelTestId}>
          {children}
        </section>
      </motion.main>
    </section>
  );
}
