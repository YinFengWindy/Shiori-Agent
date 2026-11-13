import { StoryError } from "./StoryError";
import { ArrowClockwise, ArrowLeft, Check } from "@phosphor-icons/react";
import { cx } from "@yinfengwindy/shiori-sdk";
import { resolveStoryLoadingCopy, resolveStoryLoadingPresentation, type StoryLoadingMode, type StoryLoadingPhase } from "./storyLoadingPresentation";
import { DEFAULT_STORY_MENU_BACKGROUND, StoryMenuScene } from "./StoryMenuScene";
import { storyPrimaryButtonClass, storySecondaryButtonClass } from "./storyStyles";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryLoadingScreenProps = {
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  mode: StoryLoadingMode;
  phase: StoryLoadingPhase;
  busy?: boolean;
  error?: string;
  errorDetail?: string;
  elapsedMs?: number;
  loaded?: number;
  total?: number;
  onRetry?: () => void;
  onBack?: () => void;
};

/** Renders the Story entry and save-loading transition as a checklist of real loading stages. */
export function StoryLoadingScreen({ background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, mode, phase, busy = true, error = "", errorDetail, elapsedMs = 250, loaded = 0, total = 0, onRetry, onBack }: StoryLoadingScreenProps) {
  const copy = resolveStoryLoadingCopy(mode, phase);
  const presentation = resolveStoryLoadingPresentation({ elapsedMs, loaded, total });
  const allComplete = copy.activeStage >= copy.stages.length;

  return <StoryMenuScene background={background} sharedBackdrop={sharedBackdrop} dataTestId="story-loading-screen" ariaBusy={busy} showTitle={false} animateEntrance={false}>{({ theme }) => <>
    <main className="absolute right-[clamp(20px,5vw,72px)] top-1/2 z-10 w-[min(22rem,calc(100%-40px))] -translate-y-1/2 text-[color:var(--story-wine)]" aria-label={copy.railLabel} data-testid="story-loading-rail">
      <div style={{ filter: theme.commandFilter }}>
        <h2 className="story-command-text mt-0 text-right font-serif text-3xl font-semibold leading-none">{copy.heading}</h2>
        <p className="mt-3 text-right text-xs tracking-[0.18em] opacity-75" aria-live="polite" data-testid="story-loading-current-stage">{copy.currentStage}<span className="px-2">·</span>{allComplete ? "就绪" : busy ? "载入中" : "等待开始"}</p>

        <div className="mt-8 border-t border-[color:var(--story-command-line)]" aria-label={copy.stageLabel}>
          {copy.stages.map((stage, index) => {
            const complete = index < copy.activeStage;
            const active = index === copy.activeStage;
            return <div key={stage} className="flex items-center gap-3 border-b border-[color:var(--story-command-line)] py-3" aria-current={active ? "step" : undefined} data-testid={`story-loading-stage-${index}`}>
              <span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full border border-[color:var(--story-wine)]", complete && "bg-[color:var(--story-wine)] text-[color:var(--story-on-wine)]", !complete && !active && "opacity-40")}>{complete ? <Check className="h-3 w-3" weight="bold" data-testid={`story-loading-stage-${index}-check`} /> : <span className={cx("h-1.5 w-1.5 rounded-full bg-[color:var(--story-wine)]", !active && "opacity-40")} />}</span>
              <span className={cx("text-sm", !active && !complete && "opacity-55")}>{stage}</span>
              <span className="ml-auto text-[0.72rem] tracking-[0.12em] opacity-70">
                {complete ? "完成" : active ? <span className="inline-flex items-center gap-1.5"><ArrowClockwise aria-hidden="true" className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" weight="bold" data-testid="story-loading-spinner" /><span>载入中</span></span> : "等待"}
              </span>
            </div>;
          })}
        </div>

        {presentation.kind === "progress" ? <div className="mt-6"><div className="h-1 overflow-hidden bg-[color:var(--story-line-soft)]" role="progressbar" aria-label={copy.progressLabel} aria-valuemin={0} aria-valuemax={presentation.total || 1} aria-valuenow={presentation.loaded}><div className="h-full bg-[color:var(--story-wine)] transition-[width] duration-panel" style={{ width: `${presentation.ratio * 100}%` }} /></div><div className="mt-2 flex items-center justify-between text-[0.72rem] tracking-[0.12em] opacity-70"><span>{copy.progressLabel}</span><span>{presentation.loaded} / {presentation.total}</span></div></div> : null}
      </div>

      {error ? <StoryError className="mt-5" message={error} detail={errorDetail} /> : null}
      {error && (onRetry || onBack) ? <div className="mt-5 flex items-center justify-end gap-3">{onBack ? <button className={storySecondaryButtonClass} type="button" onClick={onBack}><ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />返回</button> : null}{onRetry ? <button className={storyPrimaryButtonClass} type="button" onClick={onRetry}><ArrowClockwise className="h-4 w-4" weight="bold" aria-hidden="true" />重试</button> : null}</div> : null}
    </main>
  </>}</StoryMenuScene>;
}
