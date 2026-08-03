import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { RoleRecord } from "../shared/types";
import { StoryMainMenu } from "./StoryMenu";
import { STORY_TITLE_LOGO_URL } from "./storyStaticAssets";
import { useStoryMenuBackground } from "./useStoryMenuBackground";

type StoryLauncherProps = {
  roles?: RoleRecord[];
  busy?: boolean;
  error?: string;
  onCreateStory: () => void;
  onOpenLoad: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the cinematic Story title screen and its command rail. */
export function StoryLauncher({ roles = [], busy = false, error = "", onCreateStory, onOpenLoad, onOpenSettings, onExit }: StoryLauncherProps) {
  const reducedMotion = useReducedMotion() ?? false;
  const { url: backgroundUrl, theme } = useStoryMenuBackground(roles);

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#1D1520]" data-testid="story-launcher">
      <motion.div className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-menu-backdrop" initial={{ opacity: 0, scale: reducedMotion ? 1 : 1.06 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: reducedMotion ? 0 : 1.4, ease: "easeOut" }} style={{ backgroundImage: `url(${backgroundUrl})` }} />

      <motion.header className="absolute left-[clamp(12px,2vw,28px)] top-[clamp(12px,2vh,28px)] z-10 w-[min(18rem,calc(100vw-24px))]" data-testid="story-menu-title" initial={{ opacity: 0, y: reducedMotion ? 0 : 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reducedMotion ? 0 : 0.18, duration: reducedMotion ? 0 : 0.6, ease: "easeOut" }}><h1 className="sr-only">栞 / SHIORI</h1><div className="relative overflow-hidden"><img className="block w-full" src={STORY_TITLE_LOGO_URL} alt="" />{reducedMotion ? null : <motion.span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-white/35 blur-md" initial={{ x: "-150%" }} animate={{ x: "850%" }} transition={{ delay: 0.95, duration: 0.9, ease: "easeInOut" }} style={{ backgroundColor: theme.titleHighlight }} />}</div></motion.header>

      <div className="absolute right-[clamp(20px,5vw,72px)] top-1/2 z-10 w-[min(18rem,calc(100%-40px))] -translate-y-1/2">
        <div data-testid="story-menu-theme" style={{ filter: theme.commandFilter }}>
          <StoryMainMenu busy={busy} reducedMotion={reducedMotion} onCreateStory={onCreateStory} onOpenLoad={onOpenLoad} onOpenSettings={onOpenSettings} onExit={onExit} />
        </div>
        <AnimatePresence>{error ? <motion.div className="mt-5 border-l-2 border-[#F1A998] bg-[#4B2730]/80 px-3 py-2 text-sm text-[#FFE0D9]" role="alert" initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reducedMotion ? 0 : 0.2 }}>{error}</motion.div> : null}</AnimatePresence>
      </div>
    </section>
  );
}
