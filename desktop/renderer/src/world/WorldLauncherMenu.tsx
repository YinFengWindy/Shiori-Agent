import { ArrowLeft, ArrowRight } from "@phosphor-icons/react";
import { motion } from "motion/react";
import type { WorldSummary } from "./types";

type LauncherActions = {
  busy: boolean;
  reducedMotion: boolean;
  onCreateWorld: () => void;
  onOpenLoad: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

type StoryLoadListProps = Pick<LauncherActions, "busy" | "reducedMotion"> & {
  worlds: WorldSummary[];
  onBack: () => void;
  onLoadWorld: (worldId: string) => void;
};

const commandClass = "flex min-h-16 w-full items-center justify-end border-b border-[#3D2546]/45 py-3 text-right font-serif text-[1.7rem] font-semibold italic leading-none text-[#7A2356] [-webkit-text-stroke:0.5px_rgba(255,255,255,0.55)] [text-shadow:0_1px_0_rgba(255,255,255,0.72),0_5px_12px_rgba(93,21,51,0.28)] transition-[color,border-color,transform] hover:border-[#C65B85] hover:text-[#B12868] focus:outline-none focus-visible:border-[#A23E69] disabled:cursor-default disabled:opacity-40";
const panelTransition = { duration: 0.32, ease: "easeOut" } as const;

function commandHover(reducedMotion: boolean) {
  return reducedMotion ? undefined : { x: -8 };
}

/** Renders the Story launch commands as a cinematic, keyboard-accessible rail. */
export function StoryMainMenu({ busy, reducedMotion, onCreateWorld, onOpenLoad, onOpenSettings, onExit }: LauncherActions) {
  return (
    <motion.nav aria-label="Story menu" className="grid gap-2" data-testid="world-launcher-command-rail" initial={{ opacity: 0, x: reducedMotion ? 0 : 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reducedMotion ? 0 : 20 }} transition={panelTransition}>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onCreateWorld}>NEW STORY</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onOpenLoad}>LOAD STORY</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onOpenSettings}>SETTINGS</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onExit}>EXIT</motion.button>
    </motion.nav>
  );
}

/** Renders saved Stories as a full-page archive, not a menu-adjacent utility list. */
export function StoryLoadList({ worlds, busy, reducedMotion, onBack, onLoadWorld }: StoryLoadListProps) {
  return (
    <motion.section className="overflow-hidden border border-[#D8C7A9] bg-[#F6EEDC]/95 text-[#35424C] shadow-[0_18px_56px_rgba(25,31,37,0.24)]" data-testid="world-load-list" initial={{ opacity: 0, y: reducedMotion ? 0 : 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reducedMotion ? 0 : 18 }} transition={panelTransition}>
      <header className="flex items-start justify-between gap-5 border-b border-[#D8C7A9] px-[clamp(20px,4vw,44px)] py-7">
        <div><p className="m-0 text-[11px] font-semibold tracking-[0.2em] text-[#75858B]">RECORDS OF THE STORY</p><h2 className="m-0 mt-2 font-serif text-[clamp(2rem,5vw,3.5rem)] font-semibold leading-none text-[#354653]">Story Archive</h2></div>
        <button className="grid h-9 w-9 shrink-0 place-items-center border border-[#AFA188] text-[#3D5361] transition-colors hover:bg-[#E9DECA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#8EB0BE]" type="button" aria-label="Back to Story menu" title="Back to Story menu" onClick={onBack}><ArrowLeft /></button>
      </header>
      {worlds.length ? <div className="max-h-[min(60vh,38rem)] overflow-y-auto" aria-label="存档列表">{worlds.map((world, index) => (
        <motion.button key={world.id} className="group grid min-h-[104px] w-full grid-cols-[3rem_minmax(0,1fr)_auto] items-center gap-4 border-b border-[#DDCFB7] px-[clamp(20px,4vw,44px)] py-5 text-left transition-colors hover:bg-[#EDE2CE] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#8EB0BE] disabled:opacity-40" type="button" disabled={busy} whileHover={reducedMotion ? undefined : { x: 5 }} whileTap={reducedMotion ? undefined : { scale: 0.99 }} onClick={() => onLoadWorld(world.id)}>
          <span className="font-serif text-2xl italic text-[#92A1A1]">{String(index + 1).padStart(2, "0")}</span><span className="min-w-0"><strong className="block truncate font-serif text-xl font-semibold text-[#354653]">{world.name}</strong><span className="mt-2 block truncate text-xs text-[#70746D]">{world.currentTimeLabel}</span></span><ArrowRight className="shrink-0 text-[#526E7A] transition-transform group-hover:translate-x-1" />
        </motion.button>
      ))}</div> : <div className="grid min-h-52 place-items-center px-7 text-center"><p className="m-0 font-serif text-lg italic text-[#788078]">No story has been written yet.</p></div>}
    </motion.section>
  );
}
