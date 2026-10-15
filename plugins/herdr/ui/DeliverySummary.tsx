import { cardClass, compactButtonSizeClass, cx, primaryButtonSurfaceClass, type PluginHostServices } from "@yinfengwindy/shiori-sdk";
import { OpenPullRequestButton } from "./TaskActions";
import type { TaskDetail } from "./types";

/** A delivered run's change summary and its Draft PR, ahead of everything else. */
export function DeliverySummary({ task, host }: { task: TaskDetail; host: PluginHostServices }) {
  return (
    <section className={cx(cardClass, "grid gap-3 p-4")} aria-label="修改摘要">
      <h2 className="text-title-sm text-ink">修改摘要</h2>
      {task.summary ? <p className="whitespace-pre-wrap break-words text-body text-ink-secondary">{task.summary}</p> : null}
      {task.pr_url ? (
        <div>
          <OpenPullRequestButton url={task.pr_url} host={host} className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} />
        </div>
      ) : null}
    </section>
  );
}
