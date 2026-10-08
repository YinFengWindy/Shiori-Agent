import type { ReactNode } from "react";
import { Pause, Play, Stop } from "@phosphor-icons/react";
import { compactButtonSizeClass, compactGhostButtonClass, cx, primaryButtonSurfaceClass, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import { isRunActive, liveStatusErrors, liveStatusRows } from "./liveStatusView";
import type { LiveAction, LiveRunController } from "./useLiveRun";

type LiveRunPanelProps = {
  run: LiveRunController;
  /** Why 开始 is unavailable (`startBlockedReason`); "" blocks silently, null allows it. */
  blockedReason: string | null;
  disabled: boolean;
};

const iconClass = "h-4 w-4";

/** The run controls and the polled run status. */
export function LiveRunPanel({ run, blockedReason, disabled }: LiveRunPanelProps) {
  const host = usePluginHostServices();
  const { status, pending } = run;
  const active = isRunActive(status);
  const locked = disabled || pending !== null || status === null;
  const button = (action: LiveAction, label: string, icon: ReactNode, primary = false) => (
    <button type="button" className={primary ? cx(primaryButtonSurfaceClass, compactButtonSizeClass) : compactGhostButtonClass}
      disabled={locked || (action === "start" && blockedReason !== null)} aria-busy={pending === action || undefined}
      onClick={() => { void run.act(action); }}>{icon}{label}</button>
  );
  return <div className="grid gap-3" data-testid="live-run">
    <div className="flex flex-wrap items-center gap-2">
      {active ? null : button("start", "开始", <Play className={iconClass} weight="fill" aria-hidden="true" />, true)}
      {status?.state === "running" ? button("pause", "暂停", <Pause className={iconClass} weight="fill" aria-hidden="true" />) : null}
      {status?.state === "paused" ? button("resume", "继续", <Play className={iconClass} weight="fill" aria-hidden="true" />) : null}
      {active ? button("stop", "结束", <Stop className={iconClass} weight="fill" aria-hidden="true" />) : null}
      {!active && blockedReason ? <span className="text-body-sm text-ink-muted" data-testid="live-start-blocked">{blockedReason}</span> : null}
    </div>
    {run.actionError ? <host.ui.InlineError message={run.actionError} /> : null}
    {run.readError ? <host.ui.InlineError message={run.readError} actions={<button type="button" className={compactGhostButtonClass} onClick={run.reload}>重试</button>} /> : null}
    {status ? <>
      <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-body-sm" data-testid="live-status">
        {liveStatusRows(status).map((row) => <div key={row.label} className="contents">
          <dt className="text-ink-muted">{row.label}</dt>
          <dd className="m-0 min-w-0 break-words text-ink">{row.value}</dd>
        </div>)}
      </dl>
      {liveStatusErrors(status).map((message) => <host.ui.InlineError key={message} message={message} role="status" />)}
    </> : null}
  </div>;
}
