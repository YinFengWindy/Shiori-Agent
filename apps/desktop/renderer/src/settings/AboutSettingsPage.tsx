import { ArrowClockwise, ArrowSquareOut, Envelope, GithubLogo } from "@phosphor-icons/react";
import { cx, ghostButtonClass, primaryButtonClass } from "../shared/styles";
import { DesktopExternalLink } from "../shared/DesktopExternalLink";
import { useDesktopUpdates } from "./useDesktopUpdates";

const releaseUrl = "https://github.com/YinFengWindy/Shiori-Agent/releases/latest";
const statusLabels = {
  unsupported: null, idle: "尚未检查更新", checking: "正在检查更新…",
  current: "已是最新版本", downloading: "正在下载更新…", downloaded: "更新已就绪",
  installing: "正在重启安装…", error: "更新失败",
};

/** Shows the installed version and the desktop-owned update lifecycle. */
export function AboutSettingsPage() {
  const { state, error, check, install } = useDesktopUpdates();
  const busy = state ? ["unsupported", "checking", "downloading", "installing"].includes(state.phase) : !error;
  const downloaded = state?.phase === "downloaded";

  return (
    <div data-testid="about-settings">
      <h2 className="m-0 font-display text-headline text-ink">关于</h2>
      <div className="mt-8 flex flex-wrap items-start justify-between gap-x-10 gap-y-6 pb-8">
        <div className="flex min-w-0 shrink-0 items-center gap-4">
          <img src={new URL("../../../../../assets/shiori-app-icon.png", import.meta.url).href} alt="" className="h-16 w-16 shrink-0 object-contain" />
          <div className="min-w-0">
            <h3 className="font-display text-title text-ink">Shiori</h3>
            <p className="mt-1 break-all text-sm text-ink-muted">当前版本 {state ? `v${state.currentVersion}` : "…"}</p>
          </div>
        </div>
        <div className="min-w-0 flex-1 basis-[280px] sm:text-right" aria-label="应用更新">
          {state?.phase !== "unsupported" ? <p className="text-sm text-ink-secondary" role="status">{state ? statusLabels[state.phase] : "正在读取版本…"}</p> : null}
          {state?.latestVersion ? <p className="mt-1 break-all text-sm text-ink-muted">新版本 v{state.latestVersion}</p> : null}
          {state?.phase === "downloading" ? (
            <div className="mt-3 flex max-w-md items-center gap-3 sm:ml-auto">
              <progress aria-label="更新下载进度" max={100} value={state.progress} className="h-2 min-w-0 flex-1 accent-accent" />
              <span className="w-12 text-right text-sm tabular-nums text-ink-secondary">{Math.floor(state.progress)}%</span>
            </div>
          ) : null}
          {error ? <p role="alert" className="mt-3 break-words text-sm text-danger-text">{error}</p> : null}
          <div className={cx("flex flex-wrap gap-3 sm:justify-end", state?.phase !== "unsupported" && "mt-3")}>
            <button type="button" disabled={busy} onClick={() => void (downloaded ? install() : check())} className={cx(primaryButtonClass, "inline-flex min-h-11 items-center justify-center gap-2 text-sm")}>
              <ArrowClockwise size={18} aria-hidden="true" />
              {downloaded ? "重启并安装" : state?.phase === "error" || error ? "重新检查" : "检查更新"}
            </button>
            <DesktopExternalLink href={releaseUrl} className={cx(ghostButtonClass, "inline-flex min-h-11 items-center justify-center gap-2 text-sm no-underline")}>
              <ArrowSquareOut size={18} aria-hidden="true" />更新日志
            </DesktopExternalLink>
          </div>
        </div>
      </div>
      <dl className="grid gap-6 border-t border-line-soft py-8 text-sm">
        <div className="grid gap-2 sm:grid-cols-[120px_minmax(0,1fr)] sm:items-start">
          <dt className="flex items-center gap-2 text-ink-secondary"><GithubLogo size={18} aria-hidden="true" />GitHub</dt>
          <dd className="min-w-0"><DesktopExternalLink href="https://github.com/YinFengWindy/Shiori-Agent" className="break-all text-accent-text underline-offset-4 hover:underline">YinFengWindy/Shiori-Agent</DesktopExternalLink></dd>
        </div>
        <div className="grid gap-2 sm:grid-cols-[120px_minmax(0,1fr)] sm:items-start">
          <dt className="flex items-center gap-2 text-ink-secondary"><Envelope size={18} aria-hidden="true" />联系作者</dt>
          <dd className="min-w-0"><DesktopExternalLink href="mailto:3174898512@qq.com" className="break-all text-accent-text underline-offset-4 hover:underline">3174898512@qq.com</DesktopExternalLink></dd>
        </div>
      </dl>
    </div>
  );
}
