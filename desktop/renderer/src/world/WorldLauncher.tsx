import { ArrowLeft, FolderOpen, GearSix, Plus, SignOut } from "@phosphor-icons/react";
import { useState } from "react";
import type { WorldSummary } from "./types";

type WorldLauncherProps = {
  worlds: WorldSummary[];
  busy?: boolean;
  error?: string;
  onCreateWorld: () => void;
  onLoadWorld: (worldId: string) => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

const menuButtonClass = "group flex min-h-12 items-center gap-4 rounded-md border border-transparent px-4 py-3 text-left text-base text-[#F8F0E8] transition hover:border-white/15 hover:bg-white/10 disabled:opacity-40";

/** Galgame-style world launcher with one compact, viewport-safe menu surface. */
export function WorldLauncher({ worlds, busy = false, error = "", onCreateWorld, onLoadWorld, onOpenSettings, onExit }: WorldLauncherProps) {
  const [loadOpen, setLoadOpen] = useState(false);

  return (
    <section className="relative h-full min-h-0 overflow-hidden" data-testid="world-launcher">
      <div className="absolute inset-0 bg-cover bg-center bg-no-repeat" style={{ backgroundImage: "url('/assets/backgrounds/default-galgame-bg.png')" }} />
      <div className="absolute inset-0 bg-gradient-to-r from-white/20 via-transparent to-black/25" />

      <div className="absolute left-[clamp(16px,4vw,32px)] top-[clamp(16px,4vh,32px)] z-10">
        <h1 className="m-0 font-serif text-4xl font-bold text-[#302629] drop-shadow-[0_1px_0_rgba(255,255,255,0.75)]">Shiori</h1>
        <p className="mt-2 text-sm text-[#4B3B3E]">每一个世界，都从一次选择开始。</p>
      </div>

      <div className="absolute bottom-[clamp(16px,4vh,32px)] right-[clamp(16px,4vw,32px)] z-10 max-h-[calc(100vh-32px)] w-[min(20rem,calc(100%-32px))] overflow-y-auto rounded-md border border-white/15 bg-[#111512]/85 p-4 shadow-2xl backdrop-blur-xl">
        {loadOpen ? (
          <section data-testid="world-load-list">
            <div className="mb-3 flex items-center gap-2">
              <button className="grid h-9 w-9 place-items-center rounded-md text-white/65 hover:bg-white/10 hover:text-white" type="button" aria-label="返回 World 主菜单" onClick={() => setLoadOpen(false)}><ArrowLeft /></button>
              <h2 className="m-0 font-serif text-lg text-[#F8F0E8]">选择世界</h2>
            </div>
            {worlds.length ? (
              <div className="grid max-h-[min(16rem,calc(100vh-160px))] gap-1 overflow-y-auto">
                {worlds.map((world) => (
                  <button
                    key={world.id}
                    className="flex min-h-14 items-center gap-3 rounded-md px-3 text-left transition hover:bg-white/10 disabled:opacity-40"
                    type="button"
                    disabled={busy}
                    onClick={() => onLoadWorld(world.id)}
                  >
                    <span className="min-w-0 flex-1">
                      <strong className="block truncate text-sm font-medium text-white/90">{world.name}</strong>
                      <span className="block truncate text-xs text-white/50">{world.currentTimeLabel}</span>
                    </span>
                    <span className="text-sm font-medium text-[#DDA27E]">载入</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="m-0 py-5 text-center text-sm text-white/55">还没有已保存的世界。</p>
            )}
          </section>
        ) : (
          <nav className="grid gap-1" aria-label="World 主菜单">
            <button className={menuButtonClass} type="button" disabled={busy} onClick={onCreateWorld}><Plus className="text-[#DDA27E]" size={22} /><span className="font-serif">创建世界</span></button>
            <button className={menuButtonClass} type="button" disabled={busy} onClick={() => setLoadOpen(true)}><FolderOpen className="text-[#DDA27E]" size={22} /><span className="font-serif">加载世界</span></button>
            <button className={menuButtonClass} type="button" disabled={busy} onClick={onOpenSettings}><GearSix className="text-[#DDA27E]" size={22} /><span className="font-serif">设置</span></button>
            <button className={menuButtonClass} type="button" disabled={busy} onClick={onExit}><SignOut className="text-[#DDA27E]" size={22} /><span className="font-serif">退出</span></button>
          </nav>
        )}
        {error && (
          <div className="mt-3 rounded-md border border-[#C77A65] bg-[#492821] px-3 py-2 text-sm text-[#FFD8CD]" role="alert">
            {error}
          </div>
        )}
      </div>
    </section>
  );
}
