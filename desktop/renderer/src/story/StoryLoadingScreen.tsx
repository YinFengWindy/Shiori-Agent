import { ArrowClockwise, ArrowLeft, BookOpenText, Check } from "@phosphor-icons/react";
import { resolveStoryLoadingPresentation } from "./storyLoadingPresentation";
import { DEFAULT_STORY_MENU_BACKGROUND, StoryMenuScene } from "./StoryMenuScene";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryLoadingScreenProps = {
  background?: StoryMenuBackground;
  mode: "listing" | "story";
  busy?: boolean;
  error?: string;
  elapsedMs?: number;
  loaded?: number;
  total?: number;
  onRetry?: () => void;
  onBack?: () => void;
};

const stages = ["读取剧情", "恢复进度", "准备开场"];

/** Renders the Story entry and save-loading transition without a spinner. */
export function StoryLoadingScreen({ background = DEFAULT_STORY_MENU_BACKGROUND, mode, busy = true, error = "", elapsedMs = 250, loaded = 0, total = 0, onRetry, onBack }: StoryLoadingScreenProps) {
  const activeStage = mode === "listing" ? 0 : 1;
  const presentation = resolveStoryLoadingPresentation({ elapsedMs, loaded, total });
  const currentStage = mode === "listing" ? "读取剧情" : "恢复进度";

  return <StoryMenuScene background={background} dataTestId="story-loading-screen" ariaBusy={busy} showTitle={false} animateEntrance={false}>{({ theme }) => <>
    <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.04),rgba(255,255,255,0.02)_48%,rgba(40,20,33,0.16))]" />
    <main className="absolute right-[clamp(20px,5vw,72px)] top-1/2 z-10 w-[min(22rem,calc(100%-40px))] -translate-y-1/2" aria-label="剧情加载" data-testid="story-loading-rail">
      <div style={{ filter: theme.commandFilter }}>
        <div className="flex items-center justify-end gap-2 text-[0.68rem] uppercase tracking-[0.3em] text-[#7A2356]"><BookOpenText className="h-4 w-4" weight="duotone" /><span>Story / Loading</span></div>
        <h2 className="mt-4 text-right font-serif text-3xl font-semibold italic leading-none text-[#7A2356] [-webkit-text-stroke:0.5px_rgba(255,255,255,0.55)] [text-shadow:0_1px_0_rgba(255,255,255,0.72),0_5px_12px_rgba(93,21,51,0.28)]">进入剧情</h2>
        <p className="mt-3 text-right text-xs tracking-[0.18em] text-[#7A2356]/70">{currentStage}<span className="px-2">·</span>{busy ? "进行中" : "即将开始"}</p>

        <div className="mt-8 border-t border-[#7A2356]/35" aria-label="剧情加载阶段">
          {stages.map((stage, index) => {
            const complete = index < activeStage;
            const active = index === activeStage;
            return <div key={stage} className="flex items-center gap-3 border-b border-[#7A2356]/25 py-3" aria-current={active ? "step" : undefined} data-testid={`story-loading-stage-${index}`}>
              <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border ${complete ? "border-[#7A2356] bg-[#7A2356] text-white" : active ? "border-[#7A2356]" : "border-[#7A2356]/35"}`}>{complete ? <Check className="h-3 w-3" weight="bold" /> : <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-[#7A2356]" : "bg-[#7A2356]/25"}`} />}</span>
              <span className={`text-sm ${active || complete ? "text-[#7A2356]" : "text-[#7A2356]/45"}`}>{stage}</span>
              <span className="ml-auto text-[0.68rem] tracking-[0.12em] text-[#7A2356]/55">{complete ? "完成" : active ? "进行中" : "等待"}</span>
            </div>;
          })}
        </div>

        {presentation.kind === "progress" ? <div className="mt-6"><div className="h-1 overflow-hidden bg-[#7A2356]/15" role="progressbar" aria-valuemin={0} aria-valuemax={presentation.total || 1} aria-valuenow={presentation.loaded}><div className="h-full bg-[#7A2356] transition-[width] duration-300" style={{ width: `${presentation.ratio * 100}%` }} /></div><div className="mt-2 flex items-center justify-between text-[0.68rem] tracking-[0.12em] text-[#7A2356]/55"><span>准备素材</span><span>{presentation.loaded} / {presentation.total}</span></div></div> : null}
      </div>

      {error ? <div className="mt-6 border-l-2 border-[#A23E69] bg-white/55 px-3 py-2 text-sm text-[#6F2749]" role="alert">{error}</div> : null}
      {(error && onRetry) || onBack ? <div className="mt-5 flex items-center justify-end gap-3">{error && onRetry ? <button className="inline-flex h-9 items-center gap-2 rounded-md border border-[#7A2356]/35 bg-white/40 px-3 text-sm text-[#7A2356] transition-colors hover:bg-white/65 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" onClick={onRetry}><ArrowClockwise className="h-4 w-4" weight="bold" />重试</button> : null}{onBack ? <button className="grid h-9 w-9 place-items-center rounded-md text-[#7A2356]/65 transition-colors hover:bg-white/35 hover:text-[#7A2356] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft className="h-5 w-5" weight="bold" /></button> : null}</div> : null}
    </main>
  </>}</StoryMenuScene>;
}
