import { AnimatePresence, motion } from "motion/react";
import { StoryMainMenu } from "./StoryMenu";
import { DEFAULT_STORY_MENU_BACKGROUND, StoryMenuScene } from "./StoryMenuScene";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryLauncherProps = {
  background?: StoryMenuBackground;
  busy?: boolean;
  error?: string;
  onCreateStory: () => void;
  onOpenLoad: () => void;
  onOpenCg: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the cinematic Story title screen and its command rail. */
export function StoryLauncher({ background = DEFAULT_STORY_MENU_BACKGROUND, busy = false, error = "", onCreateStory, onOpenLoad, onOpenCg, onOpenSettings, onExit }: StoryLauncherProps) {
  return <StoryMenuScene background={background} dataTestId="story-launcher">{({ reducedMotion, theme }) => <>
    <div className="absolute right-[clamp(20px,5vw,72px)] top-1/2 z-10 w-[min(18rem,calc(100%-40px))] -translate-y-1/2">
      <div data-testid="story-menu-theme" style={{ filter: theme.commandFilter }}>
        <StoryMainMenu busy={busy} reducedMotion={reducedMotion} onCreateStory={onCreateStory} onOpenLoad={onOpenLoad} onOpenCg={onOpenCg} onOpenSettings={onOpenSettings} onExit={onExit} />
      </div>
      <AnimatePresence>{error ? <motion.div className="mt-5 border-l-2 border-[#F1A998] bg-[#4B2730]/80 px-3 py-2 text-sm text-[#FFE0D9]" role="alert" initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reducedMotion ? 0 : 0.2 }}>{error}</motion.div> : null}</AnimatePresence>
    </div>
  </>}</StoryMenuScene>;
}
