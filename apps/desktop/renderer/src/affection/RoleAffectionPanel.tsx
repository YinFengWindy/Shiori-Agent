import { cx, ghostButtonClass } from "@yinfengwindy/shiori-sdk";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { ReadError, ReadStatusLine, readStatusText } from "../shared/feedback/ReadStatus";
import { RibbonIcon } from "../shared/ui/icons";
import { AffectionCard } from "./AffectionCard";
import { resolveAffectionDisplay } from "./affectionDisplay";
import { AffectionHistoryList } from "./AffectionHistoryList";
import { AffectionOverview } from "./AffectionOverview";
import { affectionHistoryGroups } from "./affectionSelectors";
import { AffectionStagePromptEditor } from "./AffectionStagePromptEditor";
import { useAffectionHistory } from "./useAffectionHistory";

/** An uninitialized role: a ribbon mark and one plain fact. */
function AffectionEmptyState() {
  return <div className="grid justify-items-center gap-3 py-8 text-center" data-testid="role-affection-empty">
    <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent-text">
      <RibbonIcon className="h-5 w-5" />
    </span>
    <span className="text-body-sm text-ink-muted">暂无好感度</span>
  </div>;
}

type AffectionHistory = ReturnType<typeof useAffectionHistory>;

/** The 「好感」 and 「变化」 cards: the current value over its newest-first history, read-only. */
function AffectionView({ history }: { history: AffectionHistory }) {
  const { loaded } = history;
  const error = history.error ? <ReadError error={history.error} onRetry={history.retry} /> : null;
  if (!loaded) {
    return <AffectionCard title="好感">{error ?? (history.loading ? <ReadStatusLine text={readStatusText.loading} /> : null)}</AffectionCard>;
  }
  if (!loaded.affection || !resolveAffectionDisplay(loaded.affection)) {
    return <AffectionCard title="好感"><AffectionEmptyState /></AffectionCard>;
  }
  return <div className="grid gap-4" data-testid="role-affection-panel">
    <AffectionCard title="好感"><AffectionOverview summary={loaded.affection} /></AffectionCard>
    <AffectionCard title="变化">
      <AffectionHistoryList groups={affectionHistoryGroups(loaded.items)} />
      {/* Later batches load and fail under the rows already shown. */}
      {history.loading && <ReadStatusLine text={readStatusText.loading} />}
      {error}
      {!history.loading && !history.error && history.hasMore && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={history.loadMore}>加载更多</button>}
    </AffectionCard>
  </div>;
}

/** One role's tab content; keyed by role, so no batch, pending read or unsaved field carries over. */
function RoleAffectionContent({ invoke, roleId }: { invoke: DesktopInvoke; roleId: string }) {
  const history = useAffectionHistory(invoke, roleId);
  // The stage guidance is editable before initialization too; it opens on the role's current stage.
  return <div className="grid gap-4">
    <AffectionView history={history} />
    <AffectionStagePromptEditor invoke={invoke} roleId={roleId} currentStage={history.loaded?.affection?.stage ?? null} />
  </div>;
}

type RoleAffectionPanelProps = {
  roleId: string;
  bridgeReady: boolean;
  /** The desktop bridge's invoke; defaults to the preload's. */
  invoke?: DesktopInvoke;
};

/** Role-detail 「好感度」 tab: 「好感」 (value on the whole range), 「变化」 (history timeline) and 「阶段语气」 cards. */
export function RoleAffectionPanel({ roleId, bridgeReady, invoke = window.miraDesktop.invoke }: RoleAffectionPanelProps) {
  if (!bridgeReady) return <ReadStatusLine text={readStatusText.disconnected} />;
  if (!roleId) return <ReadStatusLine text={readStatusText.noRole} />;
  return <RoleAffectionContent key={roleId} invoke={invoke} roleId={roleId} />;
}
