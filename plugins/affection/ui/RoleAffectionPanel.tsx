import { Heart } from "@phosphor-icons/react";
import { cx, ghostButtonClass, type PluginHostServices, type PluginRoleAffectionComponentProps } from "@yinfengwindy/shiori-sdk";
import { AffectionCard } from "./AffectionCard";
import { resolveAffectionDisplay } from "./affectionDisplay";
import { AffectionHistoryList } from "./AffectionHistoryList";
import { AffectionOverview } from "./AffectionOverview";
import { affectionHistoryGroups } from "./affectionSelectors";
import { AffectionStagePromptEditor } from "./AffectionStagePromptEditor";
import { useAffectionHistory } from "./useAffectionHistory";

/** An uninitialized role: a heart mark and one plain fact. */
function AffectionEmptyState() {
  return <div className="grid justify-items-center gap-3 py-8 text-center" data-testid="role-affection-empty">
    <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent-text">
      <Heart className="h-5 w-5" weight="fill" />
    </span>
    <span className="text-body-sm text-ink-muted">暂无好感度</span>
  </div>;
}

type AffectionHistory = ReturnType<typeof useAffectionHistory>;

/** The 「好感」 and 「变化」 cards: the current value over its newest-first history, read-only. */
function AffectionView({ history, host }: { history: AffectionHistory; host: PluginHostServices }) {
  const { loaded } = history;
  const error = history.error ? <host.ui.InlineError message={history.error} actions={<button type="button" className={ghostButtonClass} onClick={history.retry}>重试</button>} /> : null;
  if (!loaded) {
    return <AffectionCard title="好感">{error ?? (history.loading ? <p className="m-0 text-body-sm text-ink-muted">加载中…</p> : null)}</AffectionCard>;
  }
  if (!loaded.affection || !resolveAffectionDisplay(loaded.affection)) {
    return <AffectionCard title="好感"><AffectionEmptyState /></AffectionCard>;
  }
  return <div className="grid gap-4" data-testid="role-affection-panel">
    <AffectionCard title="好感"><AffectionOverview summary={loaded.affection} /></AffectionCard>
    <AffectionCard title="变化">
      <AffectionHistoryList groups={affectionHistoryGroups(loaded.items)} />
      {history.loading && <p className="m-0 text-body-sm text-ink-muted">加载中…</p>}
      {error}
      {!history.loading && !history.error && history.hasMore && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={history.loadMore}>加载更多</button>}
    </AffectionCard>
  </div>;
}

/** One role's tab content; keyed by role, so no batch or unsaved field carries over. */
function RoleAffectionContent({ client, host, roleId }: PluginRoleAffectionComponentProps) {
  const history = useAffectionHistory(client, roleId);
  return <div className="grid gap-4">
    <AffectionView history={history} host={host} />
    <AffectionStagePromptEditor client={client} host={host} roleId={roleId} currentStage={history.loaded?.affection?.stage ?? null} />
  </div>;
}

/** Role-detail 「好感度」 tab: 「好感」, 「变化」 and 「阶段语气」. */
export function RoleAffectionPanel({ roleId, bridgeReady, client, host }: PluginRoleAffectionComponentProps) {
  if (!bridgeReady) return <p className="m-0 text-body text-ink-muted">连接已断开</p>;
  if (!roleId) return <p className="m-0 text-body text-ink-muted">请选择角色</p>;
  return <RoleAffectionContent key={roleId} client={client} host={host} roleId={roleId} bridgeReady={bridgeReady} />;
}
