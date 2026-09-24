import { ArrowClockwise, ArrowSquareOut, Envelope, GithubLogo } from "@phosphor-icons/react";
import { badgeClass, cardClass, compactButtonSizeClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../shared/styles";
import { DesktopExternalLink } from "../shared/DesktopExternalLink";
import { SettingsGroup } from "./SettingsFieldPrimitives";
import { useDesktopUpdates } from "./useDesktopUpdates";

const releaseUrl = "https://github.com/YinFengWindy/Shiori-Agent/releases/latest";
const statusLabels = {
  unsupported: null, idle: "尚未检查更新", checking: "正在检查更新…",
  current: "已是最新版本", downloading: "正在下载更新…", downloaded: "更新已就绪",
  installing: "正在重启安装…", error: "更新失败",
};
const linkClass = "break-all text-body-sm text-accent-text underline-offset-4 hover:underline";

/**
 * Shows the installed version and the desktop-owned update lifecycle. The
 * "关于" heading comes from the shared settings header, so this renders
 * content only (no heading, no top margin of its own).
 */
export function AboutSettingsPage() {
  const { state, error, check, install } = useDesktopUpdates();
  const busy = state ? ["unsupported", "checking", "downloading", "installing"].includes(state.phase) : !error;
  const downloaded = state?.phase === "downloaded";

  return (
    <div className="grid gap-7" data-testid="about-settings">
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
              {state?.phase !== "unsupported" ? <p className="m-0 text-body-sm text-ink-secondary" role="status">{state ? statusLabels[state.phase] : "正在读取版本…"}</p> : null}
              {state?.latestVersion ? <p className="m-0 mt-0.5 break-all text-caption text-ink-muted">新版本 v{state.latestVersion}</p> : null}
            </div>
            <div className="flex flex-wrap gap-2.5">
              <button type="button" disabled={busy} onClick={() => void (downloaded ? install() : check())} className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)}>
                <ArrowClockwise size={16} aria-hidden="true" />
                {downloaded ? "重启并安装" : state?.phase === "error" || error ? "重新检查" : "检查更新"}
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
          {error ? <p role="alert" className="m-0 break-words text-body-sm text-danger-text">{error}</p> : null}
        </div>
      </section>
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
  );
}
