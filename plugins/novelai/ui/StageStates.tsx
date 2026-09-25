import { useEffect, useState } from "react";
import { Key, WarningCircle } from "@phosphor-icons/react";
import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { PetalIcon, SparkleIcon } from "../../../apps/desktop/renderer/src/shared/ui/icons";
import { failurePersona, type GenerationFailure } from "./generationFailure";

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

/**
 * A failed (or impossible) generation, with the one action that fixes it
 * when there is one. Drawn by the host's inline error card
 * (`host.ui.InlineError`, runtime API 2.4.0) with the persona scene of its
 * failure kind (`failurePersona`), so 吟风 fronts
 * it while the 看板娘 is on; off, it is the plain card with the key /
 * warning glyph.
 */
export function StageFailure({ failure, onOpenSettings, onDismiss }: StageFailureProps) {
  const { ui } = usePluginHostServices();
  const tokenProblem = failure.kind === "not-configured" || failure.kind === "unauthorized";
  const action = failure.opensSettings && onOpenSettings ? (
    <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onOpenSettings}>
      去设置
    </button>
  ) : onDismiss ? (
    <button className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onDismiss}>
      知道了
    </button>
  ) : undefined;
  return (
    <div className="motion-fade-enter grid h-full place-items-center p-6" data-testid="novelai-stage-failure">
      <ui.InlineError
        layout="card"
        persona={failurePersona(failure)}
        title={failure.title}
        message={failure.message}
        glyph={tokenProblem ? Key : WarningCircle}
        glyphTone={tokenProblem ? "accent" : "danger"}
        actions={action}
        onDismiss={onDismiss}
      />
    </div>
  );
}
