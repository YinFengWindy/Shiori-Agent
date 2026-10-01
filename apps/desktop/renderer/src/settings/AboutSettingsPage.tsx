import { ArrowClockwise, ArrowSquareOut, Envelope, GithubLogo } from "@phosphor-icons/react";
import {
  badgeClass,
  cardClass,
  compactButtonSizeClass,
  cx,
  ghostButtonSurfaceClass,
  primaryButtonSurfaceClass,
} from "@shiori/sdk";
import { DesktopExternalLink } from "../shared/DesktopExternalLink";
import { InlineError } from "../shared/feedback/InlineError";
import { MascotOnStage } from "../shared/mascot/MascotOnStage";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { AboutMascot } from "./AboutMascot";
import { SettingsGroup } from "./SettingsFieldPrimitives";
import { useDesktopUpdates } from "./useDesktopUpdates";
import { updatePresentation } from "./updatePresentation";

const releaseUrl = "https://github.com/YinFengWindy/Shiori-Agent/releases/latest";
const linkClass = "break-all text-body-sm text-accent-text underline-offset-4 hover:underline";

/**
 * Shows the installed version and the desktop-owned update lifecycle. The
 * "关于" heading comes from the shared settings header, so this renders
 * content only (no heading, no top margin of its own). With the 看板娘 on,
 * 吟风 stands beside the version card (`AboutMascot`).
 */
export function AboutSettingsPage() {
  const { state, error, check, install } = useDesktopUpdates();
  const presentation = updatePresentation(state, error);
  const mascotEnabled = useMascotEnabled();

  const updateCard = (
    <section className={cx(cardClass, "grid gap-5 p-5 sm:p-6")} aria-label="应用更新">
      <div className="flex min-w-0 items-center gap-4">
        <img src={new URL("../../../../../assets/shiori-app-icon.png", import.meta.url).href} alt="" className="h-16 w-16 shrink-0 object-contain" />
        <div className="grid min-w-0 gap-1.5">
          <h3 className="m-0 font-display text-title text-ink">Shiori</h3>
          <span className={cx(badgeClass, "w-fit tabular-nums")}>当前版本 {state ? `v${state.currentVersion}` : "…"}</span>
        </div>
      </div>
      <div className="grid gap-3 border-t border-line-soft pt-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <div className="min-w-0 flex-1 basis-[200px]">
            {state?.phase !== "unsupported" ? <p className="m-0 text-body-sm text-ink-secondary" role="status">{presentation.status}</p> : null}
            {state?.latestVersion ? <p className="m-0 mt-0.5 break-all text-caption text-ink-muted">新版本 v{state.latestVersion}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2.5">
            <button type="button" disabled={presentation.busy} onClick={() => void (presentation.install ? install() : check())} className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)}>
              <ArrowClockwise size={16} aria-hidden="true" />
              {presentation.actionLabel}
            </button>
            <DesktopExternalLink href={releaseUrl} className={cx(ghostButtonSurfaceClass, compactButtonSizeClass, "no-underline")}>
              <ArrowSquareOut size={16} aria-hidden="true" />更新日志
            </DesktopExternalLink>
          </div>
        </div>
        {state?.phase === "downloading" ? (
          <div className="flex items-center gap-3">
            <progress aria-label="更新下载进度" max={100} value={state.progress} className="h-2 min-w-0 flex-1 accent-accent" />
            <span className="w-12 text-right text-body-sm tabular-nums text-ink-secondary">{Math.floor(state.progress)}%</span>
          </div>
        ) : null}
        {error ? <InlineError message={error} detail={state?.errorDetail} /> : null}
      </div>
    </section>
  );

  return (
    // 吟风 already stands beside the card: errors on this page stay plain.
    <MascotOnStage active={mascotEnabled}>
      <div className="grid gap-7" data-testid="about-settings">
        {mascotEnabled ? <AboutMascot phase={state?.phase} failed={Boolean(error)}>{updateCard}</AboutMascot> : updateCard}
        <SettingsGroup title="联系">
          <dl className="m-0 grid">
            <div className="grid gap-1 border-b border-line-soft py-4 sm:grid-cols-[140px_minmax(0,1fr)] sm:items-center">
              <dt className="flex items-center gap-2 text-body-sm text-ink-secondary"><GithubLogo size={16} aria-hidden="true" />GitHub</dt>
              <dd className="m-0 min-w-0"><DesktopExternalLink href="https://github.com/YinFengWindy/Shiori-Agent" className={linkClass}>YinFengWindy/Shiori-Agent</DesktopExternalLink></dd>
            </div>
            <div className="grid gap-1 py-4 sm:grid-cols-[140px_minmax(0,1fr)] sm:items-center">
              <dt className="flex items-center gap-2 text-body-sm text-ink-secondary"><Envelope size={16} aria-hidden="true" />联系作者</dt>
              <dd className="m-0 min-w-0"><DesktopExternalLink href="mailto:3174898512@qq.com" className={linkClass}>3174898512@qq.com</DesktopExternalLink></dd>
            </div>
          </dl>
        </SettingsGroup>
      </div>
    </MascotOnStage>
  );
}
