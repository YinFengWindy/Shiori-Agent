import { cardClass, compactButtonSizeClass, cx, ghostButtonClass, ghostButtonSurfaceClass } from "@yinfengwindy/shiori-sdk";
import { resolveAffectionDisplay } from "../chat/affectionDisplay";
import { StatusMeter } from "../chat/StatusMeter";
import { InlineError } from "../shared/feedback/InlineError";
import { RibbonIcon } from "../shared/ui/icons";
import { AffectionHistoryList } from "./AffectionHistoryList";
import { affectionHistoryRows } from "./affectionSelectors";
import { useAffectionHistory } from "./useAffectionHistory";

function StatusLine({ text }: { text: string }) {
  return <p role="status" className="m-0 text-body-sm text-ink-muted">{text}</p>;
}

/** An uninitialized role: a ribbon mark and one plain fact. */
function AffectionEmptyState() {
  return <div className="grid justify-items-center gap-3 py-12 text-center" data-testid="role-affection-empty">
    <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent">
      <RibbonIcon className="h-5 w-5" />
    </span>
    <span className="text-body-sm text-ink-muted">暂无好感度</span>
  </div>;
}

function AffectionView({ roleId }: { roleId: string }) {
  const history = useAffectionHistory(roleId);
  const page = history.history;
  const error = history.error ? <InlineError
    message={`读取失败：${history.error}`}
    actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={history.retry}>重试</button>}
  /> : null;
  if (!page) return error ?? (history.loading ? <StatusLine text="加载中…" /> : null);
  const display = resolveAffectionDisplay(page.affection);
  if (!page.affection || !display) return <AffectionEmptyState />;
  // Stacked sections; the stage prompt editor (#714) joins below the history.
  return <section className="grid gap-4" aria-label="好感度" data-testid="role-affection-panel">
    <div className={cx(cardClass, "px-5 py-4")}>
      <StatusMeter label={display.stage} value={page.affection.value} percent={display.percent} heightClass="h-2" testId="role-affection-meter" />
    </div>
    <section className="grid min-h-48 content-start gap-4 rounded-md border border-line-soft bg-surface px-5 py-4" aria-label="好感变化">
      <AffectionHistoryList rows={affectionHistoryRows(page.items)} />
      {/* Later batches load and fail under the rows already shown. */}
      {history.loading && <StatusLine text="加载中…" />}
      {error}
      {!history.loading && !history.error && history.hasMore && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={history.loadMore}>加载更多</button>}
    </section>
  </section>;
}

/** Role-detail 「好感度」 tab: current value and stage over the newest-first change history. Read-only. */
export function RoleAffectionPanel({ roleId, bridgeReady }: { roleId: string; bridgeReady: boolean }) {
  if (!bridgeReady) return <StatusLine text="连接已断开" />;
  if (!roleId) return <StatusLine text="请选择角色" />;
  // A new role starts fresh, so no batch or pending read carries over.
  return <AffectionView key={roleId} roleId={roleId} />;
}
