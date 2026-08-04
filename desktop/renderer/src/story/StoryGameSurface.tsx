import { BookOpenText, Gear, SignOut } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import { canShowStoryInput } from "./selectors";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import { advanceStoryPlayback, createStoryPlaybackState, getNextStoryBeat, getPresentedStoryBeat, syncStoryPlaybackState } from "./storyPlayback";
import { getStoryBeatPresentationFragments } from "./storyBeatPresentation";
import { formatStoryDate } from "./storyTime";
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

type StoryFragmentCursor = {
  beatId: string | null;
  index: number;
};

/** Renders the active Story as a layered visual-novel stage with one bottom dialogue band. */
export function StoryGameSurface({ story, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, busy, error, characterAvatarUrl, onSubmitInput, onOpenArchive, onOpenSettings, onExit }: StoryGameSurfaceProps) {
  const [action, setAction] = useState("");
  const [dialogueVisible, setDialogueVisible] = useState(true);
  const [playbackState, setPlaybackState] = useState(() => createStoryPlaybackState(story));
  const [fragmentCursor, setFragmentCursor] = useState<StoryFragmentCursor>({ beatId: null, index: 0 });
  const archiveWheelTriggeredRef = useRef(false);
  const synchronizedPlaybackState = syncStoryPlaybackState(playbackState, story);
  const presentedBeat = getPresentedStoryBeat(story, synchronizedPlaybackState);
  const nextBeat = getNextStoryBeat(story, synchronizedPlaybackState);
  const presentedFragments = presentedBeat ? getStoryBeatPresentationFragments(presentedBeat) : [];
  const presentedFragmentIndex = presentedBeat?.id === fragmentCursor.beatId
    ? Math.min(fragmentCursor.index, Math.max(0, presentedFragments.length - 1))
    : 0;
  const presentedFragment = presentedFragments[presentedFragmentIndex] ?? null;
  const hasNextFragment = presentedFragmentIndex < presentedFragments.length - 1;
  const storyBackgroundPath = story.backgroundResource?.status === "ready" ? story.backgroundResource.path : undefined;
  const hasStoryBackground = Boolean(storyBackgroundPath);
  const backgroundUrl = storyBackgroundPath ? toFileUrl(storyBackgroundPath) : background.url;
  const renderLocalBackdrop = !sharedBackdrop || hasStoryBackground;
  const showCharacterForeground = Boolean(characterAvatarUrl) && hasStoryBackground;
  const isGenerating = busy || story.segment.operation === "generating";
  const showPlayerInput = canShowStoryInput(story, isGenerating, hasNextFragment || nextBeat !== null);
  const isDialogueFragment = presentedFragment?.kind === "dialogue";
  const fragmentLabel = isGenerating ? "" : isDialogueFragment ? presentedBeat?.speaker ?? "" : presentedFragment ? "旁白" : "";
  const visibleText = isGenerating ? "剧情生成中..." : presentedFragment?.text || story.background;
  const canSubmit = showPlayerInput && Boolean(action.trim());

  useEffect(() => {
    setPlaybackState((current) => syncStoryPlaybackState(current, story));
  }, [story]);

  useEffect(() => {
    if (!showPlayerInput && action) setAction("");
  }, [action, showPlayerInput]);

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

  function handleSurfaceClick(event: React.MouseEvent<HTMLElement>) {
    if (event.target instanceof Element && event.target.closest("button, input, textarea, select, a")) return;
    if (isGenerating) return;
    if (presentedBeat && hasNextFragment) {
      setFragmentCursor({ beatId: presentedBeat.id, index: presentedFragmentIndex + 1 });
      return;
    }
    if (!nextBeat) return;
    setFragmentCursor({ beatId: nextBeat.id, index: 0 });
    setPlaybackState((current) => advanceStoryPlayback(story, syncStoryPlaybackState(current, story)));
  }

  return (
    <section className={cx("relative h-full min-h-0 overflow-hidden text-white", renderLocalBackdrop ? "bg-[#172128]" : "bg-transparent")} data-dialogue-visible={dialogueVisible} data-testid="story-game-surface" onClick={handleSurfaceClick} onContextMenu={handleContextMenu} onWheel={handleWheel}>
      {renderLocalBackdrop ? <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-game-backdrop" style={{ backgroundImage: `url(${backgroundUrl})` }} /> : null}
      {showCharacterForeground ? <img className="pointer-events-none absolute bottom-[clamp(11rem,22vh,16rem)] right-[clamp(4vw,10vw,12rem)] z-10 h-[min(70vh,46rem)] max-w-[42vw] object-contain object-bottom drop-shadow-[0_16px_24px_rgba(12,19,24,0.38)]" data-testid="story-game-character" src={characterAvatarUrl} alt="" /> : null}

      <div className="story-game-chrome story-game-readable absolute left-5 top-5 z-30 rounded-md px-3 py-2 text-white/85" data-testid="story-current-time"><span className="mr-2 text-xs">{formatStoryDate(story.currentStoryDate)}</span><strong className="font-serif text-lg font-semibold text-[#F4C29F]">{story.currentTimeBand}</strong></div>
      <div className="absolute right-5 top-5 z-30 flex gap-2">
        <button className="story-game-control story-game-readable grid h-10 w-10 place-items-center rounded-md text-white/85 transition-colors hover:bg-white/20 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="查看剧情记录" title="查看剧情记录" onClick={onOpenArchive}><BookOpenText /></button>
        <button className="story-game-control story-game-readable grid h-10 w-10 place-items-center rounded-md text-white/85 transition-colors hover:bg-white/20 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="剧情设置" title="剧情设置" onClick={onOpenSettings}><Gear /></button>
        <button className="story-game-control story-game-readable grid h-10 w-10 place-items-center rounded-md text-white/85 transition-colors hover:bg-white/20 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60" type="button" aria-label="返回剧情列表" title="返回剧情列表" onClick={onExit}><SignOut /></button>
      </div>

      {dialogueVisible ? <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20">
        <section className="pointer-events-auto border-t border-white/25 px-[clamp(20px,8vw,120px)] pb-[clamp(20px,4vh,40px)] pt-[clamp(32px,7vh,72px)] shadow-[inset_0_1px_0_rgba(255,255,255,0.24)] backdrop-blur-xl backdrop-saturate-150" data-testid="story-dialogue-panel" style={{ backgroundColor: `color-mix(in srgb, ${background.theme.titleHighlight} 40%, transparent)` }}>
          <div className="mx-auto max-w-6xl">
            <div className="max-w-4xl">
              {fragmentLabel ? <div className="mb-2 flex items-center gap-3"><span aria-hidden="true" className={cx("h-px w-8", isDialogueFragment ? "bg-[#F4C29F]/70" : "bg-white/40")} /><h1 className={cx("story-game-readable m-0 font-serif text-lg font-semibold tracking-wide", isDialogueFragment ? "text-[#F4C29F]" : "text-white/70")}>{fragmentLabel}</h1></div> : null}
              <p className={cx("story-game-readable m-0 min-h-14 whitespace-pre-wrap font-serif text-[clamp(1rem,1.6vw,1.25rem)] leading-8", isDialogueFragment ? "text-white" : "text-white/80 italic")} data-story-beat-id={presentedBeat?.id} data-story-fragment-index={presentedFragment ? presentedFragmentIndex : undefined} data-story-fragment-kind={presentedFragment?.kind ?? "narration"} data-testid="story-dialogue-text">{visibleText}</p>
            </div>
            {showPlayerInput ? <div className="mt-5 border-t border-white/15 pt-3">
              <AutosizeTextarea data-testid="story-player-input" className="story-game-readable min-h-10 w-full bg-transparent px-1 py-2 text-sm leading-6 text-white placeholder:text-white/70 focus:outline-none" containerClassName="min-h-10 w-full" mirrorClassName="px-1 py-2 text-sm leading-6" value={action} placeholder="写下你的行动或回应..." onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
            </div> : null}
          </div>
        </section>
      </div> : null}
      {error ? <div className="fixed bottom-5 left-1/2 z-40 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
    </section>
  );
}
