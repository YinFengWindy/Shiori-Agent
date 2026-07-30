import { FolderOpen, GearSix, Plus, SignOut, Sparkle, X } from "@phosphor-icons/react";
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

/** Renders the World game launcher before any world is loaded. */
export function WorldLauncher({ worlds, busy = false, error = "", onCreateWorld, onLoadWorld, onOpenSettings, onExit }: WorldLauncherProps) {
  const [loadOpen, setLoadOpen] = useState(false);

  return (
    <section className="relative grid h-full min-h-0 overflow-hidden bg-[#111512] text-[#F6F0E8]" data-testid="world-launcher">
      <div className="absolute inset-y-0 left-0 w-[min(48vw,620px)] border-r border-white/10 bg-[#171C18]" />
      <div className="relative mx-auto grid h-full w-full max-w-6xl grid-cols-[minmax(260px,0.8fr)_minmax(300px,1fr)] gap-12 px-10 py-12 max-[720px]:grid-cols-1 max-[720px]:gap-8 max-[720px]:px-6">
        <div className="flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-3 text-xs uppercase tracking-[0.3em] text-[#C98B65]"><Sparkle weight="fill" />World</div>
            <h1 className="mt-6 max-w-sm font-serif text-5xl leading-tight text-[#F7EBDD] max-[720px]:text-4xl">每一个世界，都从一次选择开始。</h1>
            <p className="mt-5 max-w-sm text-sm leading-7 text-white/55">选择一个入口，开始新的世界。</p>
          </div>
          <button className="inline-flex w-fit items-center gap-2 rounded-md px-1 py-2 text-sm text-white/55 hover:text-white" type="button" onClick={onExit}><SignOut />返回桌面端</button>
        </div>

        <div className="flex min-h-0 flex-col justify-center">
          <nav className="grid max-w-md gap-2" aria-label="World 主菜单">
            <button className="group flex min-h-14 items-center gap-4 border-b border-[#C98B65]/55 px-2 text-left text-lg transition hover:border-[#F1B18B] disabled:opacity-40" type="button" disabled={busy} onClick={onCreateWorld}>
              <Plus className="text-[#E5A17B]" size={22} /><span>创建世界</span><span className="ml-auto text-xs text-white/30 transition group-hover:text-white/65">01</span>
            </button>
            <button className="group flex min-h-14 items-center gap-4 border-b border-white/10 px-2 text-left text-lg transition hover:border-white/45 disabled:opacity-40" type="button" disabled={busy} onClick={() => setLoadOpen((open) => !open)}>
              <FolderOpen className="text-white/70" size={22} /><span>加载世界</span><span className="ml-auto text-xs text-white/30 transition group-hover:text-white/65">02</span>
            </button>
            <button className="group flex min-h-14 items-center gap-4 border-b border-white/10 px-2 text-left text-lg transition hover:border-white/45" type="button" disabled={busy} onClick={onOpenSettings}>
              <GearSix className="text-white/70" size={22} /><span>设置</span><span className="ml-auto text-xs text-white/30 transition group-hover:text-white/65">03</span>
            </button>
            <button className="group flex min-h-14 items-center gap-4 border-b border-white/10 px-2 text-left text-lg transition hover:border-white/45 disabled:opacity-40" type="button" disabled={busy} onClick={onExit}>
              <SignOut className="text-white/70" size={22} /><span>退出</span><span className="ml-auto text-xs text-white/30 transition group-hover:text-white/65">04</span>
            </button>
          </nav>

          {loadOpen ? (
            <section className="mt-7 max-w-md border border-white/10 bg-[#171C18]/90 p-4" data-testid="world-load-list">
              <div className="mb-3 flex items-center justify-between"><h2 className="m-0 font-serif text-base">选择世界</h2><button className="grid h-8 w-8 place-items-center rounded-md text-white/55 hover:bg-white/10 hover:text-white" type="button" aria-label="关闭世界列表" title="关闭世界列表" onClick={() => setLoadOpen(false)}><X /></button></div>
              {worlds.length ? <div className="grid max-h-56 gap-1 overflow-y-auto">{worlds.map((world) => <button key={world.id} className="flex min-h-12 items-center gap-3 rounded-md px-3 text-left transition hover:bg-white/10 disabled:opacity-40" type="button" disabled={busy} onClick={() => onLoadWorld(world.id)}><span className="min-w-0 flex-1"><strong className="block truncate text-sm font-medium">{world.name}</strong><span className="block truncate text-xs text-white/45">{world.currentTimeLabel}</span></span><span className="text-xs text-[#D49A76]">载入</span></button>)}</div> : <p className="m-0 py-5 text-sm text-white/45">还没有已保存的世界。</p>}
            </section>
          ) : null}
          {error ? <div className="mt-5 max-w-md border border-[#A95F4D] bg-[#3A201C] px-3 py-2 text-sm text-[#FFD8CD]" role="alert">{error}</div> : null}
        </div>
      </div>
    </section>
  );
}
