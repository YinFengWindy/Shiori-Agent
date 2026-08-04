import { ArrowRight, Gear, SignOut } from "@phosphor-icons/react";
import { useLayoutEffect, useRef, useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { canSubmitStoryInput } from "./selectors";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import type { StoryDetails } from "./types";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryArchiveSurfaceProps = {
  story: StoryDetails;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  busy: boolean;
  error: string;
  onSubmitInput: (content: string) => Promise<boolean>;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the immutable Story beat history and its input lane. */
export function StoryArchiveSurface({ story, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, busy, error, onSubmitInput, onOpenSettings, onExit }: StoryArchiveSurfaceProps) {
  const [input, setInput] = useState("");
  const latestBeatRef = useRef<HTMLLIElement | null>(null);
  const canSubmit = canSubmitStoryInput(story) && !busy && Boolean(input.trim());

  useLayoutEffect(() => {
    latestBeatRef.current?.scrollIntoView({ block: "nearest" });
  }, [story.beats.length]);

  async function submit() {
    if (!canSubmit) return;
    if (await onSubmitInput(input.trim())) setInput("");
  }

  return (
    <section className={`relative h-full min-h-0 overflow-hidden text-[#252A27] ${sharedBackdrop ? "bg-transparent" : "bg-[#1D1520]"}`} data-testid="story-archive-surface">
      {sharedBackdrop ? null : <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-archive-backdrop" style={{ backgroundImage: `url(${background.url})` }} />}
      <div aria-hidden="true" className={`absolute inset-0 bg-[#F1F4F2]/82 ${sharedBackdrop ? "" : "backdrop-blur-sm"}`} />
      <div className="relative z-10 grid h-full min-h-0 grid-rows-[minmax(0,1fr)]">
        <div className="pointer-events-none absolute right-5 top-5 z-10 flex gap-2">
        <button className="pointer-events-auto grid h-9 w-9 place-items-center rounded-md text-[#5D6C63] transition-colors hover:bg-white/75 hover:text-[#35433A] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7C8D82]/35" type="button" aria-label="剧情设置" title="剧情设置" onClick={onOpenSettings}><Gear /></button>
        <button className="pointer-events-auto grid h-9 w-9 place-items-center rounded-md text-[#5D6C63] transition-colors hover:bg-white/75 hover:text-[#35433A] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7C8D82]/35" type="button" aria-label="返回剧情列表" title="返回剧情列表" onClick={onExit}><SignOut /></button>
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-8">
        <main className="mx-auto grid max-w-3xl gap-8">
          <header className="border-b border-[#CCD3CE] pb-4"><p className="m-0 text-xs text-[#727A75]">剧情记录</p><h1 className="m-0 mt-1 font-serif text-2xl font-semibold">{story.title}</h1><p className="m-0 mt-2 whitespace-pre-wrap text-sm leading-6 text-[#5D6C63]">{story.background}</p><p className="m-0 mt-3 text-xs text-[#727A75]" data-testid="story-current-time">当前时段：<strong className="font-medium text-[#53675B]">{story.currentTimeBand}</strong></p></header>
          <ol className="m-0 grid list-none gap-0 border-l border-[#B9C3BC] pl-7">
            {story.beats.map((beat, index) => (
              <li key={beat.id} ref={index === story.beats.length - 1 ? latestBeatRef : undefined} className="relative pb-7">
                <span className={`absolute -left-[33px] top-1 h-3 w-3 rounded-full border-2 border-[#F1F4F2] ${beat.kind === "dialogue" ? "bg-[#A75F41]" : "bg-[#66766C]"}`} />
                <p className="m-0 mb-1 text-xs text-[#727A75]">{beat.timeBand}{beat.speaker ? ` · ${beat.speaker}` : ""}</p>
                <p className="m-0 whitespace-pre-wrap font-serif text-base leading-7 text-[#3B423E]">{beat.text}</p>
              </li>
            ))}
          </ol>
          <div className="border-t border-[#CDD4CF] pt-5">
            <div className="flex items-end gap-2 rounded-md border border-[#CCD4CE] bg-white p-2 transition focus-within:border-[#7C8D82] focus-within:ring-2 focus-within:ring-[#7C8D82]/20">
              <AutosizeTextarea className="min-h-11 w-full bg-transparent px-2 py-2 text-sm leading-6 focus:outline-none" containerClassName="min-h-11 flex-1" mirrorClassName="px-2 py-2 text-sm leading-6" value={input} placeholder={story.segment.operation === "generating" ? "剧情正在生成..." : "写下你的行动或回应..."} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
              <button className="inline-flex h-10 shrink-0 items-center gap-2 rounded-md bg-[#53675B] px-4 text-sm text-white hover:bg-[#43564B] disabled:opacity-40" type="button" aria-label="提交剧情输入" disabled={!canSubmit} onClick={() => void submit()}>提交<ArrowRight /></button>
            </div>
          </div>
        </main>
        {error ? <div className="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
        </div>
      </div>
    </section>
  );
}
