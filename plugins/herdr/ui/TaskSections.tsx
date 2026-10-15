import type { ReactNode } from "react";
import { CaretRight } from "@phosphor-icons/react";
import { cx } from "@yinfengwindy/shiori-sdk";
import { clockTime, stageLabels } from "./taskSelectors";
import type { TaskDetail } from "./types";

/** A folded section with a caret, closed by default. */
export function Section({ label, count, children }: { label: string; count?: number; children: ReactNode }) {
  return (
    <details className="group rounded-md border border-line-soft bg-surface-soft">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-body-sm font-medium text-ink-secondary [&::-webkit-details-marker]:hidden">
        <CaretRight className="h-3.5 w-3.5 text-ink-muted transition-transform duration-quick ease-out-soft group-open:rotate-90" weight="bold" aria-hidden="true" />
        {label}
        {count !== undefined ? <span className="text-caption font-normal tabular-nums text-ink-muted">{count}</span> : null}
      </summary>
      <div className="border-t border-line-soft px-3 py-3 text-body-sm">{children}</div>
    </details>
  );
}

/** 活动记录, 验证结果 and 完整需求, all folded. */
export function TaskSections({ task }: { task: TaskDetail }) {
  return (
    <div className="grid gap-2">
      {task.progress_events.length ? (
        <Section label="活动记录" count={task.progress_events.length}>
          <ol className="grid gap-2">
            {task.progress_events.map((event, index) => (
              <li key={`${event.source}:${event.sequence}:${index}`} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3">
                <time className="text-caption tabular-nums text-ink-muted" dateTime={event.observed_at}>{clockTime(event.observed_at)}</time>
                <span className="min-w-0 break-words text-ink-secondary">
                  <span className="font-medium text-ink">{stageLabels[event.stage]}</span>
                  {event.detail ? ` · ${event.detail}` : null}
                </span>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}
      {task.validation.length ? (
        <Section label="验证结果" count={task.validation.length}>
          <ul className="grid gap-3">
            {task.validation.map((check, index) => (
              <li key={index} className="grid gap-1.5">
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className={cx("flex-none font-medium", check.exit_code === 0 ? "text-success-text" : "text-danger-text")}>
                    {check.exit_code === 0 ? "通过" : "未通过"}
                  </span>
                  <code className="min-w-0 break-all font-mono text-caption text-ink-secondary">{check.argv.join(" ")}</code>
                </span>
                {check.output ? (
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-surface p-2 font-mono text-caption text-ink-secondary [overflow-wrap:anywhere]">{check.output}</pre>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section label="完整需求">
        <p className="whitespace-pre-wrap break-words text-ink-secondary">{task.requirement}</p>
      </Section>
    </div>
  );
}
