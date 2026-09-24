import { useEffect, useState } from "react";
import { Key, WarningCircle, X } from "@phosphor-icons/react";
import { compactButtonSizeClass, compactPressableClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { PetalIcon, SparkleIcon } from "../../../apps/desktop/renderer/src/shared/ui/icons";
import type { GenerationFailure } from "./generationFailure";

/** Nothing generated yet for this role: the brand motif on the glass stage. */
export function StageEmpty() {
  return (
    <div className="motion-fade-enter grid h-full place-items-center p-6" data-testid="novelai-stage-empty">
      <div className="grid justify-items-center gap-4 text-center">
        <span className="relative grid h-24 w-24 place-items-center rounded-full border border-white/80 bg-white/70 text-accent shadow-soft">
          <SparkleIcon className="h-10 w-10" />
          <span className="absolute -right-1 top-2 text-lavender"><SparkleIcon className="h-4 w-4" /></span>
          <span className="absolute -bottom-1 left-1 text-accent-text opacity-70"><PetalIcon className="h-5 w-5" /></span>
        </span>
        <span className="font-display text-title text-ink">画布还空着</span>
      </div>
    </div>
  );
}

function useElapsedSeconds(): number {
  const [startedAt] = useState(() => Date.now());
  const [now, setNow] = useState(startedAt);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return Math.floor((now - startedAt) / 1000);
}

/** In flight: a frame in the requested aspect with a light sweep and twinkling sparkles. */
export function StageGenerating({ aspect }: { aspect: number }) {
  const elapsed = useElapsedSeconds();
  return (
    <div className="grid h-full place-items-center p-6 [container-type:size]" data-testid="novelai-stage-generating" role="status" aria-live="polite">
      <div
        className="nai-shimmer grid place-items-center"
        style={{ aspectRatio: String(aspect), width: `min(100cqw, calc(100cqh * ${aspect}))` }}
      >
        <div className="relative z-[1] grid justify-items-center gap-3 text-center">
          <span className="relative h-14 w-16 text-accent">
            <span className="nai-twinkle absolute left-3 top-2"><SparkleIcon className="h-9 w-9" /></span>
            <span className="nai-twinkle nai-twinkle-late absolute right-0 top-0 text-lavender"><SparkleIcon className="h-4 w-4" /></span>
            <span className="nai-twinkle nai-twinkle-later absolute bottom-0 left-0 text-accent-text"><SparkleIcon className="h-3.5 w-3.5" /></span>
          </span>
          <span className="text-body font-medium text-ink">生成中</span>
          <span className="text-caption tabular-nums text-ink-muted">{elapsed} 秒</span>
        </div>
      </div>
    </div>
  );
}

type StageFailureProps = {
  failure: GenerationFailure;
  onOpenSettings?: () => void;
  onDismiss?: () => void;
};

/** A failed (or impossible) generation, with the one action that fixes it when there is one. */
export function StageFailure({ failure, onOpenSettings, onDismiss }: StageFailureProps) {
  const tokenProblem = failure.kind === "not-configured" || failure.kind === "unauthorized";
  return (
    <div className="motion-fade-enter grid h-full place-items-center p-6" data-testid="novelai-stage-failure" role="alert">
      <div className="surface-glass-strong relative grid w-full max-w-[420px] justify-items-center gap-3 rounded-xl px-6 py-7 text-center">
        {onDismiss ? (
          <button
            className={cx(compactPressableClass, "absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink")}
            type="button"
            aria-label="关闭"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
        <span className={cx(
          "grid h-12 w-12 place-items-center rounded-full",
          tokenProblem ? "bg-accent-softer text-accent-text" : "bg-danger-soft text-danger-text",
        )}>
          {tokenProblem ? <Key className="h-6 w-6" weight="duotone" aria-hidden="true" /> : <WarningCircle className="h-6 w-6" weight="duotone" aria-hidden="true" />}
        </span>
        <span className="font-display text-title-sm text-ink">{failure.title}</span>
        {failure.message ? (
          <span className="max-h-28 overflow-y-auto break-words text-body-sm text-ink-muted [overflow-wrap:anywhere]">{failure.message}</span>
        ) : null}
        {failure.opensSettings && onOpenSettings ? (
          <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass, "mt-1")} type="button" onClick={onOpenSettings}>
            去设置
          </button>
        ) : onDismiss ? (
          <button className={cx(ghostButtonSurfaceClass, compactButtonSizeClass, "mt-1")} type="button" onClick={onDismiss}>
            知道了
          </button>
        ) : null}
      </div>
    </div>
  );
}
