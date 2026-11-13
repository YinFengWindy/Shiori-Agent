import { StoryError } from "./StoryError";
import { ArrowClockwise, BookOpenText, CaretDown, EyeSlash, Gear, House, Pause, Play } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { AutosizeTextarea, cx, useLatestRef, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import { canShowStoryInput, isStoryRoleInCurrentScene, selectActiveStoryVisualResource } from "./selectors";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import { advanceStoryPlayback, createStoryPlaybackState, getNextStoryBeat, getPresentedStoryBeat, syncStoryPlaybackState } from "./storyPlayback";
import { getStoryBeatPresentationFragments } from "./storyBeatPresentation";
import { storyAutoPlayDelayMs, storyTextCharactersPerSecond, updateStoryPreferences, useStoryPreferences, useStoryReducedMotion } from "./storyPreferences";
import { storyStageControlClass } from "./storyStyles";
import { formatStoryDate } from "./storyTime";
import type { StoryDetails } from "./types";
import type { StoryMenuBackground } from "./useStoryMenuBackground";
import { useStoryTypewriter } from "./useStoryTypewriter";

type StoryGameSurfaceProps = {
  story: StoryDetails;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  busy: boolean;
  error: string;
  errorDetail?: string;
  characterAvatarUrl?: string;
  onSubmitInput: (content: string) => Promise<boolean>;
  onRegenerateCg?: (resourceId: string) => void | Promise<boolean>;
  onOpenArchive: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

type StoryFragmentCursor = {
  beatId: string | null;
  index: number;
};

/** Minimum gap between two wheel-driven advances, so one flick reads one line. */
const WHEEL_ADVANCE_COOLDOWN_MS = 350;
const advanceKeys = new Set([" ", "Enter", "ArrowDown", "PageDown"]);
const archiveKeys = new Set(["ArrowUp", "PageUp"]);

function resolveDialogueSpeakerName(speaker: string | null | undefined, roleName: string | undefined) {
  const normalizedSpeaker = speaker?.trim() ?? "";
  if (normalizedSpeaker === "角色") return roleName?.trim() || normalizedSpeaker;
  return normalizedSpeaker;
}

function isTextEntryTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest("input, textarea, select, [contenteditable='true'], [role='dialog']"));
}

/** Renders the active Story as a layered visual-novel stage with one bottom dialogue band. */
export function StoryGameSurface({ story, background = DEFAULT_STORY_MENU_BACKGROUND, busy, error, errorDetail, characterAvatarUrl, onSubmitInput, onRegenerateCg, onOpenArchive, onOpenSettings, onExit }: StoryGameSurfaceProps) {
  const [action, setAction] = useState("");
  const [dialogueVisible, setDialogueVisible] = useState(true);
  const [playbackState, setPlaybackState] = useState(() => createStoryPlaybackState(story));
  const [fragmentCursor, setFragmentCursor] = useState<StoryFragmentCursor>({ beatId: null, index: 0 });
  const archiveWheelTriggeredRef = useRef(false);
  const lastWheelAdvanceRef = useRef(0);
  const preferences = useStoryPreferences();
  const reducedMotion = useStoryReducedMotion();
  const host = usePluginHostServices();
  const synchronizedPlaybackState = syncStoryPlaybackState(playbackState, story);
  const presentedBeat = getPresentedStoryBeat(story, synchronizedPlaybackState);
  const nextBeat = getNextStoryBeat(story, synchronizedPlaybackState);
  const presentedFragments = presentedBeat ? getStoryBeatPresentationFragments(presentedBeat) : [];
  const presentedFragmentIndex = presentedBeat?.id === fragmentCursor.beatId
    ? Math.min(fragmentCursor.index, Math.max(0, presentedFragments.length - 1))
    : 0;
  const presentedFragment = presentedFragments[presentedFragmentIndex] ?? null;
  const hasNextFragment = presentedFragmentIndex < presentedFragments.length - 1;
  const storyCgResource = [...story.cgGallery].reverse().find((resource) => resource.kind === "cg" && resource.sceneKey === story.currentScene.key && resource.path) ?? null;
  const storyVisualResource = selectActiveStoryVisualResource(story);
  const storyBackgroundPath = storyVisualResource?.path;
  const backgroundUrl = storyBackgroundPath ? host.assets.url(storyBackgroundPath) : null;
  const currentSceneLabel = (story.currentScene.name ?? "").trim() || "未命名场景";
  const showCharacterForeground = Boolean(characterAvatarUrl)
    && storyVisualResource?.visualType === "scene"
    && isStoryRoleInCurrentScene(story);
  const hasGeneratingCg = story.cgGallery.some((resource) => resource.kind === "cg" && resource.status === "generating");
  const isGenerating = busy || story.segment.operation === "generating";
  const isDialogueFragment = presentedFragment?.kind === "dialogue";
  const fragmentLabel = isGenerating
    ? ""
    : isDialogueFragment
      ? resolveDialogueSpeakerName(presentedBeat?.speaker, story.roleSnapshot.name)
      : presentedFragment
        ? "旁白"
        : "";
  const fullText = isGenerating ? "剧情生成中..." : presentedFragment?.text || story.background;
  const typewriterKey = isGenerating ? "generating" : `${presentedBeat?.id ?? "background"}:${presentedFragmentIndex}`;
  const typewriter = useStoryTypewriter(fullText, typewriterKey, isGenerating ? null : storyTextCharactersPerSecond(preferences));
  const hasMoreToRead = hasNextFragment || nextBeat !== null;
  const showContinueMark = !isGenerating && typewriter.complete && hasMoreToRead;
  const showPlayerInput = typewriter.complete && canShowStoryInput(story, isGenerating, hasMoreToRead);
  const canSubmit = showPlayerInput && Boolean(action.trim());

  useEffect(() => {
    setPlaybackState((current) => syncStoryPlaybackState(current, story));
  }, [story]);

  useEffect(() => {
    if (!showPlayerInput && action) setAction("");
  }, [action, showPlayerInput]);

  /** One reading step: reveal the dialogue, finish the typing line, or move to the next line. */
  function advance() {
    if (!dialogueVisible) {
      setDialogueVisible(true);
      return;
    }
    if (isGenerating) return;
    if (!typewriter.complete) {
      typewriter.finish();
      return;
    }
    if (presentedBeat && hasNextFragment) {
      setFragmentCursor({ beatId: presentedBeat.id, index: presentedFragmentIndex + 1 });
      return;
    }
    if (!nextBeat) return;
    setFragmentCursor({ beatId: nextBeat.id, index: 0 });
    setPlaybackState((current) => advanceStoryPlayback(story, syncStoryPlaybackState(current, story)));
  }

  const advanceRef = useLatestRef(advance);
  const openArchiveRef = useLatestRef(onOpenArchive);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || isTextEntryTarget(event.target)) return;
      const onButton = event.target instanceof Element && Boolean(event.target.closest("button, a"));
      if (advanceKeys.has(event.key) && !(onButton && (event.key === " " || event.key === "Enter"))) {
        event.preventDefault();
        advanceRef.current();
      } else if (archiveKeys.has(event.key)) {
        event.preventDefault();
        openArchiveRef.current();
      } else if (event.key === "Escape") {
        setDialogueVisible(true);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [advanceRef, openArchiveRef]);

  const autoPlayDelay = storyAutoPlayDelayMs(preferences);
  useEffect(() => {
    if (!preferences.autoPlay || !showContinueMark || !dialogueVisible) return;
    const timer = setTimeout(() => advanceRef.current(), autoPlayDelay);
    return () => clearTimeout(timer);
  }, [advanceRef, autoPlayDelay, dialogueVisible, preferences.autoPlay, showContinueMark, typewriterKey]);

  async function submit() {
    if (!canSubmit) return;
    if (await onSubmitInput(action.trim())) setAction("");
  }

  function handleContextMenu(event: React.MouseEvent<HTMLElement>) {
    event.preventDefault();
    setDialogueVisible((visible) => !visible);
  }

  function handleWheel(event: React.WheelEvent<HTMLElement>) {
    if (event.deltaY === 0 || isTextEntryTarget(event.target)) return;
    if (event.deltaY < 0) {
      if (archiveWheelTriggeredRef.current) return;
      archiveWheelTriggeredRef.current = true;
      onOpenArchive();
      return;
    }
    const now = Date.now();
    if (now - lastWheelAdvanceRef.current < WHEEL_ADVANCE_COOLDOWN_MS) return;
    lastWheelAdvanceRef.current = now;
    advance();
  }

  function handleSurfaceClick(event: React.MouseEvent<HTMLElement>) {
    if (event.target instanceof Element && event.target.closest("button, input, textarea, select, a")) return;
    advance();
  }

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[color:var(--story-stage)] text-[color:var(--story-stage-ink)]" data-dialogue-visible={dialogueVisible} data-testid="story-game-surface" onClick={handleSurfaceClick} onContextMenu={handleContextMenu} onWheel={handleWheel}>
      <div aria-hidden="true" className="absolute inset-0 bg-[color:var(--story-stage)] bg-cover bg-center bg-no-repeat" data-testid="story-game-backdrop" style={backgroundUrl ? { backgroundImage: `url(${backgroundUrl})` } : undefined} />
      <AnimatePresence initial={false} mode="wait">
        {showCharacterForeground && characterAvatarUrl ? <motion.img
          key={`${story.currentScene.key}:${characterAvatarUrl}`}
          className="pointer-events-none absolute -bottom-6 right-[clamp(4vw,10vw,12rem)] z-10 h-[min(78vh,52rem)] max-w-[48vw] origin-bottom-right object-contain object-bottom [filter:drop-shadow(var(--story-shadow-character))]"
          data-testid="story-game-character"
          src={characterAvatarUrl}
          alt=""
          initial={{ opacity: 0, transform: reducedMotion ? "scale(1.2)" : "translateY(8px) scale(1.18)" }}
          animate={{ opacity: 1, transform: "translateY(0) scale(1.2)" }}
          exit={{ opacity: 0, transform: reducedMotion ? "scale(1.2)" : "translateY(-4px) scale(1.2)" }}
          transition={{ duration: reducedMotion ? 0.12 : 0.28, ease: "easeOut" }}
        /> : null}
      </AnimatePresence>

      {dialogueVisible ? <>
        <div className="story-game-chrome story-game-readable absolute left-5 top-5 z-30 flex min-w-0 max-w-[calc(100vw-22rem)] flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-3 py-2 text-[color:var(--story-stage-ink-muted)]" data-testid="story-current-time"><span className="text-xs">{formatStoryDate(story.currentStoryDate)}</span><strong className="font-serif text-lg font-semibold text-[color:var(--story-stage-gold)]">{story.currentTimeBand}</strong><span aria-hidden="true" className="h-4 w-px bg-[color:var(--story-stage-line)]" /><span className="min-w-0 max-w-full truncate text-xs" data-testid="story-current-scene" title={`场景：${currentSceneLabel}`}>场景：{currentSceneLabel}</span></div>
        <div className="absolute right-5 top-5 z-30 flex gap-2">
          <button className={storyStageControlClass} type="button" aria-label="查看剧情记录" title="查看剧情记录（↑）" onClick={onOpenArchive}><BookOpenText /></button>
          <button className={storyStageControlClass} type="button" aria-label="自动播放" aria-pressed={preferences.autoPlay} title="自动播放" onClick={() => updateStoryPreferences({ autoPlay: !preferences.autoPlay })}>{preferences.autoPlay ? <Pause weight="fill" /> : <Play />}</button>
          <button className={storyStageControlClass} type="button" aria-label="隐藏对话框" title="隐藏对话框（右键）" onClick={() => setDialogueVisible(false)}><EyeSlash /></button>
          {storyCgResource && onRegenerateCg ? <button className={storyStageControlClass} type="button" aria-label="重新生成当前 CG" title="重新生成当前 CG" disabled={busy || hasGeneratingCg} onClick={() => { void onRegenerateCg(storyCgResource.id); }}><ArrowClockwise /></button> : null}
          <button className={storyStageControlClass} type="button" aria-label="剧情设置" title="剧情设置" onClick={onOpenSettings}><Gear /></button>
          <button className={storyStageControlClass} type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onExit}><House /></button>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20">
          <section className="pointer-events-auto border-t border-[color:var(--story-stage-line)] px-[clamp(20px,8vw,120px)] pb-[clamp(20px,4vh,40px)] pt-[clamp(12px,2vh,24px)] shadow-[var(--story-shadow-band)] backdrop-blur-xl backdrop-saturate-150" data-testid="story-dialogue-panel" style={{ backgroundColor: `color-mix(in srgb, ${background.theme.titleHighlight} 40%, transparent)` }}>
            <div className="mx-auto max-w-6xl">
              <div className="max-w-4xl">
                {fragmentLabel ? <div className="mb-2 flex items-center gap-3"><span aria-hidden="true" className={cx("h-px w-8", isDialogueFragment ? "bg-[color:var(--story-stage-gold)]" : "bg-[color:var(--story-stage-line)]")} /><h1 className={cx("story-game-readable m-0 font-serif text-lg font-semibold tracking-wide", isDialogueFragment ? "text-[color:var(--story-stage-gold)]" : "text-[color:var(--story-stage-ink-muted)]")}>{fragmentLabel}</h1></div> : null}
                <p className={cx("story-game-readable m-0 min-h-14 whitespace-pre-wrap font-serif text-[clamp(1rem,1.6vw,1.25rem)] leading-8", isDialogueFragment ? "text-[color:var(--story-stage-ink)]" : "italic text-[color:var(--story-stage-ink-muted)]")} data-story-beat-id={presentedBeat?.id} data-story-fragment-index={presentedFragment ? presentedFragmentIndex : undefined} data-story-fragment-kind={presentedFragment?.kind ?? "narration"} data-story-text-complete={typewriter.complete} data-testid="story-dialogue-text">
                  <span className="sr-only">{fullText}</span>
                  {/* The untyped remainder stays in layout (transparent) so the band never grows while typing. */}
                  <span aria-hidden="true">{typewriter.visibleText}<span className="opacity-0">{typewriter.hiddenText}</span></span>
                  {showContinueMark ? <CaretDown aria-hidden="true" className="story-continue-mark ml-2 inline-block h-4 w-4 align-baseline text-[color:var(--story-stage-gold)]" data-testid="story-continue-mark" weight="bold" /> : null}
                </p>
              </div>
              {showPlayerInput ? <div className="mt-3 border-t border-[color:var(--story-stage-line)] pt-2">
                {/* Borderless by design (`border-0` / `focus:shadow-none`): the dialogue band itself is the field. */}
                <AutosizeTextarea data-testid="story-player-input" autoFocus className="story-game-readable min-h-10 w-full border-0 bg-transparent px-1 py-2 outline-none focus:shadow-none text-sm leading-6 text-[color:var(--story-stage-ink)] placeholder:text-[color:var(--story-stage-ink-muted)]" containerClassName="min-h-10 w-full" mirrorClassName="px-1 py-2 text-sm leading-6" value={action} placeholder="写下你的行动或回应..." onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
              </div> : null}
            </div>
          </section>
        </div>
      </> : null}
      {error ? <StoryError className="fixed bottom-5 left-1/2 z-40 w-[min(32rem,calc(100%-2rem))] -translate-x-1/2" message={error} detail={errorDetail} /> : null}
    </section>
  );
}
