import { ArrowLeft, ArrowRight } from "@phosphor-icons/react";
import { motion } from "motion/react";
import type { StorySummary } from "./types";

type LauncherActions = {
  busy: boolean;
  reducedMotion: boolean;
  onCreateStory: () => void;
  onOpenLoad: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

type StoryLoadListProps = Pick<LauncherActions, "busy" | "reducedMotion"> & {
  stories: StorySummary[];
  onBack: () => void;
  onLoadStory: (storyId: string) => void;
};

const commandClass = "flex min-h-16 w-full items-center justify-end border-b border-[#3D2546]/45 py-3 text-right font-serif text-[1.7rem] font-semibold italic leading-none text-[#7A2356] [-webkit-text-stroke:0.5px_rgba(255,255,255,0.55)] [text-shadow:0_1px_0_rgba(255,255,255,0.72),0_5px_12px_rgba(93,21,51,0.28)] transition-[color,border-color,transform] hover:border-[#C65B85] hover:text-[#B12868] focus:outline-none focus-visible:border-[#A23E69] disabled:cursor-default disabled:opacity-40";
const panelTransition = { duration: 0.28, ease: "easeOut" } as const;

function commandHover(reducedMotion: boolean) {
  return reducedMotion ? undefined : { x: -8 };
}

/** Renders the Story launch commands as a cinematic, keyboard-accessible rail. */
export function StoryMainMenu({ busy, reducedMotion, onCreateStory, onOpenLoad, onOpenSettings, onExit }: LauncherActions) {
  return (
    <motion.nav aria-label="Story menu" className="grid gap-2" data-testid="story-launcher-command-rail" initial={{ opacity: 0, x: reducedMotion ? 0 : 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reducedMotion ? 0 : 20 }} transition={panelTransition}>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onCreateStory}>NEW STORY</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onOpenLoad}>LOAD STORY</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onOpenSettings}>SETTINGS</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onExit}>EXIT</motion.button>
    </motion.nav>
  );
}

/** Renders saved Stories as a romance visual-novel album. */
export function StoryLoadList({ stories, busy, reducedMotion, onBack, onLoadStory }: StoryLoadListProps) {
  return (
    <motion.section className="w-full text-[#4A2738]" data-testid="story-load-list" initial={{ opacity: 0, x: reducedMotion ? 0 : -24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reducedMotion ? 0 : 20 }} transition={panelTransition}>
      <div className="mb-6 flex items-center gap-3">
        <button className="grid h-9 w-9 place-items-center rounded-md border border-[#C785A0]/55 bg-[#FFF8FC]/55 text-[#8F355C] transition-colors hover:border-[#B64B75] hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="Back to Story menu" onClick={onBack}><ArrowLeft /></button>
        <h2 className="m-0 font-serif text-2xl font-semibold italic text-[#7A2356] [-webkit-text-stroke:0.4px_rgba(255,255,255,0.65)] [text-shadow:0_1px_0_rgba(255,255,255,0.8),0_4px_10px_rgba(93,21,51,0.2)]">STORY ALBUM</h2>
      </div>
      {stories.length ? (
        <div className="grid max-h-[min(22rem,calc(100vh-184px))] gap-0 overflow-y-auto border-y border-[#DDA9BE]/65 pr-1">
          {stories.map((story) => (
            <motion.button key={story.storyId} className="flex min-h-20 items-center gap-3 border-b border-[#E8BED0]/75 bg-[#FFF8FC]/55 px-4 py-3 text-left transition-colors hover:bg-white/75 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0] disabled:opacity-40" type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={() => onLoadStory(story.storyId)}>
              <span className="min-w-0 flex-1"><strong className="block truncate font-serif text-base text-[#5E2841]">{story.title}</strong><span className="mt-1 block truncate text-xs text-[#8B6676]">{story.createdAt}</span></span>
              <ArrowRight className="shrink-0 text-[#B64B75]" />
            </motion.button>
          ))}
        </div>
      ) : <p className="m-0 border-y border-[#DDA9BE]/65 py-5 text-sm text-[#8B6676]">No saved stories yet.</p>}
    </motion.section>
  );
}
