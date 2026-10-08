import { cardClass, cx, ghostButtonClass } from "@yinfengwindy/shiori-sdk";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { ReadError, ReadFrame, ReadStatusLine, readStatusText } from "../shared/feedback/ReadStatus";
import { RibbonIcon } from "../shared/ui/icons";
import { StatusMeter } from "../shared/ui/StatusMeter";
import { resolveAffectionDisplay } from "./affectionDisplay";
import { AffectionHistoryList } from "./AffectionHistoryList";
import { AffectionStagePromptEditor } from "./AffectionStagePromptEditor";
import { affectionHistoryRows } from "./affectionSelectors";
import { useAffectionHistory } from "./useAffectionHistory";

/** An uninitialized role: a ribbon mark and one plain fact. */
function AffectionEmptyState() {
  return <div className="grid justify-items-center gap-3 py-12 text-center" data-testid="role-affection-empty">
    <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent-text">
      <RibbonIcon className="h-5 w-5" />
    </span>
    <span className="text-body-sm text-ink-muted">暂无好感度</span>
  </div>;
}

function AffectionView({ invoke, roleId }: { invoke: DesktopInvoke; roleId: string }) {
  const history = useAffectionHistory(invoke, roleId);
  const { loaded } = history;
  const error = history.error ? <ReadError error={history.error} onRetry={history.retry} /> : null;
  if (!loaded) return error ?? (history.loading ? <ReadStatusLine text={readStatusText.loading} /> : null);
  const display = resolveAffectionDisplay(loaded.affection);
  if (!loaded.affection || !display) return <AffectionEmptyState />;
  return <section className="grid gap-4" aria-label="好感度" data-testid="role-affection-panel">
    <div className={cx(cardClass, "px-5 py-4")}>
      <StatusMeter label={display.stage} value={loaded.affection.value} percent={display.percent} heightClass="h-2" testId="role-affection-meter" />
    </div>
    <ReadFrame label="好感变化">
      <AffectionHistoryList rows={affectionHistoryRows(loaded.items)} />
      {/* Later batches load and fail under the rows already shown. */}
      {history.loading && <ReadStatusLine text={readStatusText.loading} />}
      {error}
      {!history.loading && !history.error && history.hasMore && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={history.loadMore}>加载更多</button>}
    </ReadFrame>
  </section>;
}

type RoleAffectionPanelProps = {
  roleId: string;
  bridgeReady: boolean;
  /** The desktop bridge's invoke; defaults to the preload's. */
  invoke?: DesktopInvoke;
};

/** Role-detail 「好感度」 tab: current value and stage over the newest-first change history, then the per-stage guidance. */
export function RoleAffectionPanel({ roleId, bridgeReady, invoke = window.miraDesktop.invoke }: RoleAffectionPanelProps) {
  if (!bridgeReady) return <ReadStatusLine text={readStatusText.disconnected} />;
  if (!roleId) return <ReadStatusLine text={readStatusText.noRole} />;
  // A new role starts fresh, so no batch, pending read or unsaved field carries over.
  // The stage guidance sits below the value and history, and is editable before initialization too.
  return <div className="grid gap-4">
    <AffectionView key={`history:${roleId}`} invoke={invoke} roleId={roleId} />
    <AffectionStagePromptEditor key={`prompts:${roleId}`} invoke={invoke} roleId={roleId} />
  </div>;
}
