import { ArrowRight, BookOpenText, Gear, SignOut } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import { canSubmitStoryInput } from "./selectors";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import type { StoryDetails } from "./types";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryGameSurfaceProps = {
  story: StoryDetails;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  busy: boolean;
  error: string;
  characterAvatarUrl?: string;
  onSubmitInput: (content: string) => Promise<boolean>;
  onOpenArchive: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the active Story as a layered visual-novel stage with one bottom dialogue band. */
export function StoryGameSurface({ story, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, busy, error, characterAvatarUrl, onSubmitInput, onOpenArchive, onOpenSettings, onExit }: StoryGameSurfaceProps) {
  const [action, setAction] = useState("");
  const [dialogueVisible, setDialogueVisible] = useState(true);
  const archiveWheelTriggeredRef = useRef(false);
  const latestBeat = story.beats[story.beats.length - 1] ?? null;
  const storyBackgroundPath = story.backgroundResource?.status === "ready" ? story.backgroundResource.path : undefined;
  const hasStoryBackground = Boolean(storyBackgroundPath);
  const backgroundUrl = storyBackgroundPath ? toFileUrl(storyBackgroundPath) : background.url;
  const renderLocalBackdrop = !sharedBackdrop || hasStoryBackground;
  const showCharacterForeground = Boolean(characterAvatarUrl) && hasStoryBackground;
  const speakerName = latestBeat?.speaker ?? "";
  const visibleText = latestBeat?.text || story.background;
  const canSubmit = canSubmitStoryInput(story) && !busy && Boolean(action.trim());

  async function submit() {
    if (!canSubmit) return;
    if (await onSubmitInput(action.trim())) setAction("");
  }

  function handleContextMenu(event: React.MouseEvent<HTMLElement>) {
    event.preventDefault();
    setDialogueVisible((visible) => !visible);
  }

  function handleWheel(event: React.WheelEvent<HTMLElement>) {
    if (archiveWheelTriggeredRef.current || event.deltaY === 0) return;
    event.preventDefault();
    archiveWheelTriggeredRef.current = true;
    onOpenArchive();
  }

  return (
    <section className={cx("relative h-full min-h-0 overflow-hidden text-white", renderLocalBackdrop ? "bg-[#172128]" : "bg-transparent")} data-dialogue-visible={dialogueVisible} data-testid="story-game-surface" onContextMenu={handleContextMenu} onWheel={handleWheel}>
      {renderLocalBackdrop ? <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-game-backdrop" style={{ backgroundImage: `url(${backgroundUrl})` }} /> : null}
      {showCharacterForeground ? <img className="pointer-events-none absolute bottom-[clamp(11rem,22vh,16rem)] right-[clamp(4vw,10vw,12rem)] z-10 h-[min(70vh,46rem)] max-w-[42vw] object-contain object-bottom drop-shadow-[0_16px_24px_rgba(12,19,24,0.38)]" data-testid="story-game-character" src={characterAvatarUrl} alt="" /> : null}

      <div className="absolute left-5 top-5 z-30 text-white/75" data-testid="story-current-time"><span className="mr-2 text-xs">当前时段</span><strong className="font-serif text-lg font-semibold text-[#F4C29F]">{story.currentTimeBand}</strong></div>
      <div className="absolute right-5 top-5 z-30 flex gap-2">
        <button className="grid h-10 w-10 place-items-center rounded-md bg-black/20 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/40 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="查看剧情记录" title="查看剧情记录" onClick={onOpenArchive}><BookOpenText /></button>
        <button className="grid h-10 w-10 place-items-center rounded-md bg-black/20 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/40 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="剧情设置" title="剧情设置" onClick={onOpenSettings}><Gear /></button>
        <button className="grid h-10 w-10 place-items-center rounded-md bg-black/20 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/40 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="返回剧情列表" title="返回剧情列表" onClick={onExit}><SignOut /></button>
      </div>

      {dialogueVisible ? <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20">
        <section className="pointer-events-auto border-t border-white/20 px-[clamp(20px,8vw,120px)] pb-[clamp(20px,4vh,40px)] pt-[clamp(32px,7vh,72px)] shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] backdrop-blur-xl backdrop-saturate-150" data-testid="story-dialogue-panel" style={{ backgroundColor: `color-mix(in srgb, ${background.theme.titleHighlight} 60%, transparent)` }}>
          <div className="mx-auto max-w-6xl">
            <div className="max-w-4xl">
              {speakerName ? <div className="mb-2 flex items-center gap-3"><span aria-hidden="true" className="h-px w-8 bg-[#F4C29F]/70" /><h1 className="m-0 font-serif text-lg font-semibold tracking-wide text-[#F4C29F]">{speakerName}</h1></div> : null}
              <p className="m-0 min-h-14 whitespace-pre-wrap font-serif text-[clamp(1rem,1.6vw,1.25rem)] leading-8 text-white" data-testid="story-dialogue-text">{visibleText}</p>
            </div>
            <div className="mt-5 flex items-end gap-3 border-t border-white/15 pt-3">
              <AutosizeTextarea className="min-h-10 w-full bg-transparent px-1 py-2 text-sm leading-6 text-white placeholder:text-white/55 focus:outline-none" containerClassName="min-h-10 flex-1" mirrorClassName="px-1 py-2 text-sm leading-6" value={action} placeholder={story.segment.operation === "generating" ? "剧情正在生成..." : "写下你的行动或回应..."} onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
              <button className="grid h-10 w-10 shrink-0 place-items-center border border-[#EAB48C] bg-[#BA704B] text-white transition-colors hover:bg-[#A05A39] disabled:cursor-default disabled:opacity-40" type="button" aria-label="提交剧情行动" title="提交剧情行动" disabled={!canSubmit} onClick={() => void submit()}><ArrowRight /></button>
            </div>
            {story.segment.operation === "generating" ? <p className="m-0 mt-2 text-xs text-[#F1C4A8]">剧情正在生成。</p> : null}
          </div>
        </section>
      </div> : null}
      {error ? <div className="fixed bottom-5 left-1/2 z-40 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
    </section>
  );
}
