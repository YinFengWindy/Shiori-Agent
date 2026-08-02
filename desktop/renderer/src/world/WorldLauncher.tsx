import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import type { WorldSummary } from "./types";
import { StoryLoadList, StoryMainMenu } from "./WorldLauncherMenu";
import { WORLD_MENU_BACKGROUND_URL } from "./worldStaticAssets";

type WorldLauncherProps = {
  worlds: WorldSummary[];
  busy?: boolean;
  error?: string;
  onCreateWorld: () => void;
  onLoadWorld: (worldId: string) => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the cinematic Story title screen and switches between its two menu states. */
export function WorldLauncher({ worlds, busy = false, error = "", onCreateWorld, onLoadWorld, onOpenSettings, onExit }: WorldLauncherProps) {
  const [loadOpen, setLoadOpen] = useState(false);
  const reducedMotion = useReducedMotion() ?? false;

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#1D1520]" data-testid="world-launcher">
      <motion.div className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-menu-backdrop" initial={{ opacity: 0, scale: reducedMotion ? 1 : 1.06 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: reducedMotion ? 0 : 1.4, ease: "easeOut" }} style={{ backgroundImage: `url(${WORLD_MENU_BACKGROUND_URL})` }} />
      <div className="absolute inset-y-0 right-0 w-[min(47%,38rem)] bg-[#2A1827]/35" />
      <div className="absolute inset-0 bg-black/10" />

      <motion.header className="absolute left-[clamp(20px,5vw,64px)] top-[clamp(24px,6vh,72px)] z-10" data-testid="story-menu-title" initial={{ opacity: 0, y: reducedMotion ? 0 : 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reducedMotion ? 0 : 0.18, duration: reducedMotion ? 0 : 0.6, ease: "easeOut" }}><p className="m-0 font-serif text-sm text-[#894562]">故事</p><h1 className="mt-1 font-serif text-5xl font-bold text-[#352431] drop-shadow-[0_1px_0_rgba(255,255,255,0.8)]">Shiori</h1></motion.header>

      <div className="absolute right-[clamp(20px,5vw,72px)] top-1/2 z-10 w-[min(22rem,calc(100%-40px))] -translate-y-1/2 border-l border-white/30 pl-5">
        <AnimatePresence initial={false} mode="wait">
          {loadOpen ? <StoryLoadList key="load" worlds={worlds} busy={busy} reducedMotion={reducedMotion} onBack={() => setLoadOpen(false)} onLoadWorld={onLoadWorld} /> : <StoryMainMenu key="menu" busy={busy} reducedMotion={reducedMotion} onCreateWorld={onCreateWorld} onOpenLoad={() => setLoadOpen(true)} onOpenSettings={onOpenSettings} onExit={onExit} />}
        </AnimatePresence>
        <AnimatePresence>{error ? <motion.div className="mt-5 border-l-2 border-[#F1A998] bg-[#4B2730]/80 px-3 py-2 text-sm text-[#FFE0D9]" role="alert" initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reducedMotion ? 0 : 0.2 }}>{error}</motion.div> : null}</AnimatePresence>
      </div>
    </section>
  );
}
