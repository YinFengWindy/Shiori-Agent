import { cx } from "@yinfengwindy/shiori-sdk";
import { clockTime, stageLabels, stageOrder } from "./taskSelectors";
import type { TaskDetail } from "./types";

/** 准备 → 分析 → 实现 → 验证 → 创建 PR, the reported stage highlighted, then the latest report. */
export function StageTrack({ task }: { task: TaskDetail }) {
  const current = task.stage ? stageOrder.indexOf(task.stage) : -1;
  return (
    <section className="grid gap-2" aria-label="阶段">
      <ol className="grid grid-cols-5 gap-1.5">
        {stageOrder.map((stage, index) => (
          <li
            key={stage}
            className={cx("grid gap-1.5 text-caption", index === current ? "font-medium text-accent-text" : "text-ink-muted")}
            aria-current={index === current ? "step" : undefined}
          >
            <span className={cx("h-1 rounded-full", index === current ? "bg-accent" : index < current ? "bg-accent-soft" : "bg-line-soft")} />
            {stageLabels[stage]}
          </li>
        ))}
      </ol>
      {task.progress_detail || task.progress_updated_at ? (
        <p className="flex min-w-0 items-baseline gap-2 text-body-sm text-ink-secondary">
          <span className="min-w-0 flex-1 break-words">{task.progress_detail}</span>
          <time className="flex-none text-caption tabular-nums text-ink-muted" dateTime={task.progress_updated_at}>{clockTime(task.progress_updated_at)}</time>
        </p>
      ) : null}
      {task.progress_notice ? <p className="text-caption text-warning-text">{task.progress_notice}</p> : null}
    </section>
  );
}
