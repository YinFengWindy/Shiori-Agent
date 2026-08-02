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

const commandClass = "flex min-h-14 w-full items-center justify-end border-b border-[#3D2546]/45 py-3 text-right font-serif text-2xl text-[#2C1E34] transition-[color,border-color,transform] hover:border-[#C65B85] hover:text-[#A23E69] focus:outline-none focus-visible:border-[#A23E69] disabled:cursor-default disabled:opacity-40";
const panelTransition = { duration: 0.28, ease: "easeOut" } as const;

function commandHover(reducedMotion: boolean) {
  return reducedMotion ? undefined : { x: -8 };
}

/** Renders the Story launch commands as a cinematic, keyboard-accessible rail. */
export function StoryMainMenu({ busy, reducedMotion, onCreateWorld, onOpenLoad, onOpenSettings, onExit }: LauncherActions) {
  return (
    <motion.nav
      aria-label="剧情主菜单"
      className="grid gap-2"
      data-testid="world-launcher-command-rail"
      initial={{ opacity: 0, x: reducedMotion ? 0 : 28 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: reducedMotion ? 0 : 20 }}
      transition={panelTransition}
    >
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onCreateWorld}>创建剧情</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onOpenLoad}>加载剧情</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onOpenSettings}>设置</motion.button>
      <motion.button className={commandClass} type="button" disabled={busy} whileHover={commandHover(reducedMotion)} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={onExit}>退出</motion.button>
    </motion.nav>
  );
}

/** Renders saved Stories without losing the title-screen transition context. */
export function StoryLoadList({ worlds, busy, reducedMotion, onBack, onLoadWorld }: StoryLoadListProps) {
  return (
    <motion.section
      data-testid="world-load-list"
      initial={{ opacity: 0, x: reducedMotion ? 0 : -24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: reducedMotion ? 0 : 20 }}
      transition={panelTransition}
    >
      <div className="mb-5 flex items-center gap-3">
        <button className="grid h-9 w-9 place-items-center rounded-md border border-white/20 text-white/80 transition hover:border-[#F3AEC6] hover:text-white focus:outline-none focus-visible:border-[#F3AEC6]" type="button" aria-label="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button>
        <h2 className="m-0 font-serif text-xl text-[#FFF5F1]">选择剧情</h2>
      </div>
      {worlds.length ? (
        <div className="grid max-h-[min(22rem,calc(100vh-184px))] gap-2 overflow-y-auto pr-1">
          {worlds.map((world) => (
            <motion.button
              key={world.id}
              className="flex min-h-16 items-center gap-3 border-l-2 border-white/20 px-3 py-3 text-left text-white transition-colors hover:border-[#F3AEC6] hover:bg-white/10 focus:outline-none focus-visible:border-[#F3AEC6] disabled:opacity-40"
              type="button"
              disabled={busy}
              whileHover={commandHover(reducedMotion)}
              whileTap={reducedMotion ? undefined : { scale: 0.98 }}
              onClick={() => onLoadWorld(world.id)}
            >
              <span className="min-w-0 flex-1"><strong className="block truncate text-sm font-medium">{world.name}</strong><span className="block truncate text-xs text-white/55">{world.currentTimeLabel}</span></span>
              <ArrowRight className="shrink-0 text-[#F3AEC6]" />
            </motion.button>
          ))}
        </div>
      ) : <p className="m-0 py-5 text-sm text-white/65">还没有已保存的剧情。</p>}
    </motion.section>
  );
}
