import { ArrowsClockwise } from "@phosphor-icons/react";
import { useState } from "react";
import { ChatTypingSparkles } from "../chat/ChatTypingSparkles";
import { MascotHalfFigure } from "../shared/mascot/MascotFigure";
import { pickMascotLine, startupFailedLine, startupGreetingLines, startupSlowLine, startupTimeBandAt } from "../shared/mascot/mascotLines";
import { MascotSpeechBubble } from "../shared/mascot/MascotSpeech";
import { SceneBackdrop } from "../shared/scene/SceneBackdrop";
import { scenePhaseAt } from "../shared/scene/timeOfDay";
import { compactButtonSizeClass, cx, primaryButtonSurfaceClass } from "../shared/styles";
import { TitleBar } from "../shell/TitleBar";
import type { StartupSplashPhase } from "./startupSplashPhase";

const noop = () => undefined;

type StartupSplashProps = {
  phase: StartupSplashPhase;
  /** The backend answered: fade out (the workspace is already rendered underneath). */
  leaving: boolean;
  windowMaximized: boolean;
  /** 「重启连接」 on a failed startup: the same restart as the offline banner's. */
  onRestart: () => Promise<void>;
};

/**
 * The startup splash (#362 stage 10): while the local backend boots, 吟风
 * stands a little right of centre over the time-of-day scene, with one line
 * and the brand loading sparkles under her. A failed startup swaps the
 * sparkles for 「重启连接」. It covers the whole window (with a minimal title
 * bar, like the first-run guide) above the workspace, which keeps loading
 * underneath. Her lines are an owner-approved exception to 「不写叙述文字」.
 * Styles: `.startup-splash*` in styles.css.
 */
export function StartupSplash({ phase, leaving, windowMaximized, onRestart }: StartupSplashProps) {
  // Read once: a splash crossing a band boundary keeps its scene and greeting.
  const [scene] = useState(() => scenePhaseAt(new Date()));
  const [greeting] = useState(() => pickMascotLine(startupGreetingLines[startupTimeBandAt(new Date())]));
  const [restarting, setRestarting] = useState(false);
  const line = phase === "failed" ? startupFailedLine : phase === "slow" ? startupSlowLine : greeting;

  async function restart() {
    setRestarting(true);
    try {
      await onRestart();
    } finally {
      setRestarting(false);
    }
  }

  return (
    <div className="startup-splash fixed inset-0 z-[55] flex flex-col overflow-hidden text-ink" data-leaving={leaving || undefined} data-testid="startup-splash" data-phase={phase}>
      <SceneBackdrop phase={scene} />
      <div className="relative z-[2] shrink-0">
        <TitleBar minimal sidebarCollapsed windowMaximized={windowMaximized} canGoBack={false} canGoForward={false} canRefreshSession={false}
          onToggleSidebar={noop} onGoBack={noop} onGoForward={noop} onRefreshSession={noop} />
      </div>
      <main className="startup-splash-stage relative z-[1] grid min-h-0 flex-1">
        <div className="startup-splash-cast mascot-enter">
          <MascotHalfFigure expression={line.expression} className="startup-splash-figure" />
          <div className="startup-splash-caption">
            <MascotSpeechBubble line={line} tail="top" live />
            {phase === "failed" ? (
              <button type="button" className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} disabled={restarting} onClick={() => void restart()}>
                <ArrowsClockwise className={cx("h-4 w-4", restarting && "animate-spin motion-reduce:animate-none")} weight="bold" aria-hidden="true" />
                重启连接
              </button>
            ) : (
              <span className="startup-splash-loader" role="status" aria-label="正在启动">
                <ChatTypingSparkles />
              </span>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
