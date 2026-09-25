import { ArrowsClockwise, Plugs } from "@phosphor-icons/react";
import { useLayoutEffect, useRef, useState } from "react";
import { MascotFaceAvatar } from "../shared/mascot/MascotFigure";
import { bridgeOfflineLine } from "../shared/mascot/mascotLines";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { cx } from "../shared/styles";
import { useBridgeOfflineFeedbackFilter } from "./bridgeOfflineFeedback";

type BridgeOfflineBannerProps = {
  health: string;
  /** Last failure reason reported by the bridge; offered as a tooltip, not body text (it can be a traceback). */
  bridgeError: string;
  onRestart: () => Promise<void>;
};

/** Whether the offline banner should be on screen for this health / restart state. */
export function shouldShowBridgeOfflineBanner(health: string, restarting: boolean): boolean {
  // The first connect after launch is also "connecting"; only a real drop
  // (or a restart the user asked for from this banner) shows the banner.
  return health === "offline" || restarting;
}

/**
 * Persistent strip shown while the local bridge is down. Unlike a toast it
 * stays until the connection is back, because every bridge-backed control
 * (sending, the model menu, role lists, settings) is disabled meanwhile and
 * this is the one place that says why and offers the way back.
 */
/**
 * CSS variable holding how much vertical space the banner takes below the
 * title bar (unset when hidden). `FeedbackToaster` offsets its stack by it so
 * toasts never cover the banner.
 */
export const statusBannerOffsetVariable = "--status-banner-offset";

export function BridgeOfflineBanner({ health, bridgeError, onRestart }: BridgeOfflineBannerProps) {
  const [restarting, setRestarting] = useState(false);
  const bannerRef = useRef<HTMLDivElement | null>(null);
  const visible = shouldShowBridgeOfflineBanner(health, restarting);
  const mascotEnabled = useMascotEnabled();
  // While this banner explains the outage, toasts that only repeat it are dropped.
  useBridgeOfflineFeedbackFilter(visible, bridgeError);

  useLayoutEffect(() => {
    const root = document.documentElement;
    const banner = bannerRef.current;
    if (!visible || !banner) {
      root.style.removeProperty(statusBannerOffsetVariable);
      return undefined;
    }
    // Height plus the strip's bottom margin, kept current if the text wraps.
    const publish = () => {
      const marginBottom = Number.parseFloat(getComputedStyle(banner).marginBottom) || 0;
      root.style.setProperty(statusBannerOffsetVariable, `${banner.offsetHeight + marginBottom}px`);
    };
    publish();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(publish);
    observer?.observe(banner);
    return () => {
      observer?.disconnect();
      root.style.removeProperty(statusBannerOffsetVariable);
    };
  }, [visible]);

  if (!visible) return null;

  async function restart() {
    setRestarting(true);
    try {
      await onRestart();
    } finally {
      setRestarting(false);
    }
  }

  return (
    <div
      ref={bannerRef}
      className="motion-fade-enter mx-3 mb-1.5 flex items-center gap-3 rounded-md bg-warning-soft px-3 py-1.5 text-body-sm text-warning-text"
      role="status"
      data-testid="bridge-offline-banner"
    >
      {/* With the 看板娘 on, 吟风 says the first sentence (an owner-approved line, #362 stage 10). */}
      {mascotEnabled ? (
        <MascotFaceAvatar expression={bridgeOfflineLine.expression} className="-my-0.5" />
      ) : (
        <Plugs className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
      )}
      <span className="min-w-0 flex-1 truncate" title={bridgeError.split("\n", 1)[0] || undefined}>
        {mascotEnabled ? <span className="font-medium" data-testid="bridge-offline-mascot-line">{bridgeOfflineLine.text} </span> : null}
        <span className={cx(mascotEnabled && "opacity-80")}>
          {restarting ? "正在重新连接本地服务…" : "与本地服务的连接已断开，聊天、角色与设置暂时无法使用。"}
        </span>
      </span>
      <button
        type="button"
        className={cx(
          "inline-flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-body-sm font-medium text-warning-text transition-colors hover:bg-surface-hover",
          "disabled:cursor-default disabled:opacity-60",
        )}
        disabled={restarting}
        onClick={() => void restart()}
      >
        <ArrowsClockwise className={cx("h-3.5 w-3.5", restarting && "animate-spin motion-reduce:animate-none")} weight="bold" aria-hidden="true" />
        重启连接
      </button>
    </div>
  );
}
