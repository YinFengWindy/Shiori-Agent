import { ArrowRight, BookOpenText, Gear, SignOut } from "@phosphor-icons/react";
import { useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { toFileUrl } from "../shared/format";
import { canSubmitStoryInput } from "./selectors";
import type { StoryDetails } from "./types";
import { STORY_MENU_BACKGROUND_URL } from "./storyStaticAssets";

type StoryGameSurfaceProps = {
  story: StoryDetails;
  busy: boolean;
  error: string;
  characterAvatarUrl?: string;
  onSubmitInput: (content: string) => Promise<boolean>;
  onOpenArchive: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the active Story as a visual-novel stage while the Day view remains an archive. */
export function StoryGameSurface({ story, busy, error, characterAvatarUrl, onSubmitInput, onOpenArchive, onOpenSettings, onExit }: StoryGameSurfaceProps) {
  const [action, setAction] = useState("");
  const latestBeat = story.beats[story.beats.length - 1] ?? null;
  const backgroundUrl = story.backgroundResource?.status === "ready" && story.backgroundResource.path
    ? toFileUrl(story.backgroundResource.path)
    : STORY_MENU_BACKGROUND_URL;
  const speakerName = latestBeat?.speaker ?? "";
  const visibleText = latestBeat?.text || story.background;
  const canSubmit = canSubmitStoryInput(story) && !busy && Boolean(action.trim());

  async function submit() {
    if (!canSubmit) return;
    if (await onSubmitInput(action.trim())) setAction("");
  }

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#172128] text-white" data-testid="story-game-surface">
      <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-game-backdrop" style={{ backgroundImage: `url(${backgroundUrl})` }} />
      <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-2/3 bg-[linear-gradient(0deg,rgba(13,20,25,0.9),rgba(13,20,25,0.35)_44%,transparent)]" />
      {characterAvatarUrl ? <img className="pointer-events-none absolute bottom-[clamp(10rem,20vh,15rem)] right-[clamp(4vw,10vw,12rem)] z-10 h-[min(64vh,42rem)] max-w-[42vw] object-contain object-bottom drop-shadow-[0_16px_24px_rgba(12,19,24,0.38)]" src={characterAvatarUrl} alt="" /> : null}

      <div className="absolute left-5 top-5 z-30 text-white/75" data-testid="story-current-time"><span className="mr-2 text-xs">当前时段</span><strong className="font-serif text-lg font-semibold text-[#F4C29F]">{story.currentTimeBand}</strong></div>
      <div className="absolute right-5 top-5 z-30 flex gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-md bg-black/20 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/40 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="查看剧情记录" title="查看剧情记录" onClick={onOpenArchive}><BookOpenText /></button>
        <button className="grid h-10 w-10 place-items-center rounded-md bg-black/20 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/40 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="剧情设置" title="剧情设置" onClick={onOpenSettings}><Gear /></button>
        <button className="grid h-10 w-10 place-items-center rounded-md bg-black/20 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/40 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="返回剧情列表" title="返回剧情列表" onClick={onExit}><SignOut /></button>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-[clamp(20px,8vw,120px)] pb-[clamp(24px,6vh,64px)]">
        <section className="pointer-events-auto mx-auto max-w-5xl border border-white/25 bg-[#10191E]/75 px-[clamp(20px,4vw,40px)] py-6 shadow-[0_16px_46px_rgba(5,11,15,0.32)] backdrop-blur-md">
          {speakerName ? <h1 className="m-0 mb-3 font-serif text-xl font-semibold text-[#F4C29F]">{speakerName}</h1> : null}
          <p className="m-0 min-h-16 whitespace-pre-wrap font-serif text-[clamp(1rem,1.6vw,1.25rem)] leading-8 text-white">{visibleText}</p>
          <div className="mt-5 flex items-end gap-3 border-t border-white/15 pt-4">
            <AutosizeTextarea className="min-h-11 w-full bg-transparent px-1 py-2 text-sm leading-6 text-white placeholder:text-white/55 focus:outline-none" containerClassName="min-h-11 flex-1" mirrorClassName="px-1 py-2 text-sm leading-6" value={action} placeholder={story.segment.operation === "generating" ? "剧情正在生成..." : "写下你的行动或回应..."} onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
            <button className="inline-flex h-10 shrink-0 items-center gap-2 border border-[#EAB48C] bg-[#BA704B] px-4 text-sm font-semibold text-white transition-colors hover:bg-[#A05A39] disabled:cursor-default disabled:opacity-40" type="button" aria-label="提交剧情行动" disabled={!canSubmit} onClick={() => void submit()}>提交<ArrowRight /></button>
          </div>
          {story.segment.operation === "generating" ? <p className="m-0 mt-3 text-xs text-[#F1C4A8]">剧情正在生成。</p> : null}
        </section>
      </div>
      {error ? <div className="fixed bottom-5 left-1/2 z-40 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
    </section>
  );
}
