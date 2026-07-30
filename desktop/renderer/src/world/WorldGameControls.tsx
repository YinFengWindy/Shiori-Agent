import { ArrowClockwise, List, Pause, Play, SkipForward, X } from "@phosphor-icons/react";
import { useState } from "react";

type WorldGameControlsProps = {
  worldName: string;
  paused: boolean;
  onPause: () => void;
  onResume: () => void;
  onSkip: () => void;
  onRedraw?: () => void;
  onOpenTimeline: () => void;
  onExitWorkspace: () => void;
};

/** Owns the small set of controls that can interrupt a World performance. */
export function WorldGameControls({ worldName, paused, onPause, onResume, onSkip, onRedraw, onOpenTimeline, onExitWorkspace }: WorldGameControlsProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  function openMenu() {
    setMenuOpen(true);
    if (!paused) onPause();
  }

  function closeMenu() {
    setMenuOpen(false);
  }

  function resumeFromMenu() {
    setMenuOpen(false);
    onResume();
  }

  return (
    <>
      <header className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-5 py-4 text-white">
        <span className="font-serif text-sm text-white/75">{worldName}</span>
        <div className="flex items-center gap-2">
          {onRedraw ? <button className="grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="重绘镜头" title="重绘镜头" onClick={onRedraw}><ArrowClockwise /></button> : null}
          <button className="grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label={paused ? "继续演出" : "暂停演出"} title={paused ? "继续演出" : "暂停演出"} onClick={paused ? onResume : onPause}>
            {paused ? <Play /> : <Pause />}
          </button>
          <button className="grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="跳过当前演出" title="跳过当前演出" onClick={onSkip}><SkipForward /></button>
          <button className="grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="打开演出菜单" title="打开演出菜单" onClick={openMenu}><List /></button>
        </div>
      </header>
      {menuOpen ? (
        <aside className="absolute right-5 top-20 z-30 grid w-64 gap-2 rounded-md border border-white/15 bg-[#171A18]/95 p-3 text-white shadow-2xl backdrop-blur-md" role="dialog" aria-label="演出菜单">
          <div className="flex items-center justify-between px-1 pb-1"><strong className="font-serif text-base">演出菜单</strong><button className="grid h-8 w-8 place-items-center rounded-md text-white/70 hover:bg-white/10" type="button" aria-label="关闭演出菜单" title="关闭演出菜单" onClick={closeMenu}><X /></button></div>
          <button className="flex h-10 items-center rounded-md px-3 text-left text-sm hover:bg-white/10" type="button" onClick={() => { setMenuOpen(false); onOpenTimeline(); }}>打开时间线</button>
          <button className="flex h-10 items-center rounded-md px-3 text-left text-sm hover:bg-white/10" type="button" onClick={onExitWorkspace}>返回世界管理</button>
          <button className="flex h-10 items-center rounded-md px-3 text-left text-sm hover:bg-white/10" type="button" onClick={resumeFromMenu}>继续演出</button>
        </aside>
      ) : null}
    </>
  );
}
