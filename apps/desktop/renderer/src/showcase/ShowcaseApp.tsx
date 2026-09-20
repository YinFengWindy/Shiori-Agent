import { lazy, Suspense, useEffect, useState } from "react";
import { ArrowCounterClockwise, ArrowLeft, ArrowSquareOut, BookOpen } from "@phosphor-icons/react";
import { ShowcaseChat } from "./ShowcaseChat";
import { createDemoChat } from "./demoChat";
import { createDemoStoryHost } from "./demoStoryHost";
import { demoAvatar } from "./demoContent";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { ghostButtonClass, iconButtonClass } from "../shared/styles";

const ShowcaseStory = lazy(() => import("./ShowcaseStory"));

/** Compose a static product preview from the original chat and Story entry points. */
export function ShowcaseApp() {
  const [chat] = useState(() => createDemoChat(localStorage));
  const [storyHost] = useState(() => createDemoStoryHost(localStorage));
  const [storyOpen, setStoryOpen] = useState(() => location.hash === "#story");
  const [confirmReset, setConfirmReset] = useState(false);
  useEffect(() => {
    const navigate = () => setStoryOpen(location.hash === "#story");
    window.addEventListener("hashchange", navigate);
    return () => { window.removeEventListener("hashchange", navigate); chat.dispose(); void storyHost.client.dispose(); };
  }, [chat, storyHost]);
  const openStory = () => { location.hash = "story"; };
  const openChat = () => { location.hash = "chat"; };
  return <div className="showcase-root grid h-dvh min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-surface-app text-ink">
    <header className="showcase-banner flex min-h-14 flex-wrap items-center gap-3 border-b border-line-soft px-3 py-2">
      {storyOpen ? <button className={iconButtonClass} type="button" aria-label="返回聊天" onClick={openChat}><ArrowLeft className="h-4 w-4" /></button> : <img src={demoAvatar} alt="" className="h-8 w-8 rounded-md" />}
      <div className="min-w-0"><div className="font-display text-title-sm font-semibold">Shiori <span className="ml-2 text-caption font-normal text-accent-text">交互演示</span></div><p className="m-0 text-caption text-ink-muted">{storyOpen ? "预设剧情与素材 · 自由输入仅记录操作" : "预设对话与状态 · 输入不会调用 AI"}</p></div>
      <div className="ml-auto flex items-center gap-2">
        {!storyOpen ? <button type="button" className={`${ghostButtonClass} showcase-story-entry flex items-center gap-2 !px-3 !py-2`} onClick={openStory}><BookOpen className="h-4 w-4" />故事模式</button> : null}
        <button type="button" className={iconButtonClass} aria-label="重置演示" onClick={() => setConfirmReset(true)}><ArrowCounterClockwise className="h-4 w-4" /></button>
        <a className={`${ghostButtonClass} flex items-center gap-2 !px-3 !py-2 text-body`} href="https://github.com/YinFengWindy/Shiori-Agent/releases/latest" target="_blank" rel="noreferrer">下载 Shiori<ArrowSquareOut className="h-4 w-4" /></a>
      </div>
    </header>
    <div className="min-h-0 min-w-0 overflow-hidden">
      {storyOpen ? <Suspense fallback={<div role="status" className="grid h-full place-items-center text-ink-muted">正在打开故事…</div>}><ShowcaseStory host={storyHost} onExit={openChat} /></Suspense> : <ShowcaseChat chat={chat} onStory={openStory} />}
    </div>
    <ConfirmDialog open={confirmReset} title="重新开始演示？" description="此浏览器保存的演示对话和故事进度将被清除。" confirmLabel="重新开始" onClose={() => setConfirmReset(false)} onConfirm={() => { chat.reset(); storyHost.reset(); location.reload(); }} />
  </div>;
}
