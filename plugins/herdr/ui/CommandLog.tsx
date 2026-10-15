import { cx } from "@yinfengwindy/shiori-sdk";
import { Section } from "./TaskSections";
import { clockTime } from "./taskSelectors";
import type { AgentCommand } from "./types";

/** How a command's outcome reads; a sent one carries no mark. */
const statusMarks: Record<AgentCommand["status"], { label: string; tone: string } | null> = {
  sending: { label: "发送中", tone: "text-ink-muted" },
  sent: null,
  unconfirmed: { label: "未确认送达", tone: "text-warning-text" },
  failed: { label: "未发送", tone: "text-danger-text" },
};

/** Whether a delivered command is reported to the agent's handling role. */
const reportMarks: Record<AgentCommand["report"], { label: string; tone: string }> = {
  none: { label: "不回报", tone: "text-ink-muted" },
  pending: { label: "待回报", tone: "text-ink-muted" },
  reported: { label: "已回报", tone: "text-ink-muted" },
  failed: { label: "回报失败", tone: "text-danger-text" },
};

/** Only commands that reached, or may have reached, the agent are reported. */
function reportMark(command: AgentCommand) {
  return command.status === "sent" || command.status === "unconfirmed" ? reportMarks[command.report] : null;
}

/** Who sent a command: 「你」 for the panel's user, otherwise the role's name. */
function commandSender(command: AgentCommand) {
  return command.source.kind === "user" ? "你" : command.source.role_name || command.source.role_id;
}

/** The agent's command record in this Shiori run, oldest first, folded like the task's records. */
export function CommandLog({ commands }: { commands: AgentCommand[] }) {
  if (!commands.length) return null;
  return (
    <Section label="指令记录" count={commands.length}>
      <ol className="grid gap-2" aria-label="指令记录">
        {commands.map((command) => {
          const mark = statusMarks[command.status];
          const report = reportMark(command);
          return (
            <li key={command.id} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3">
              <time className="text-caption tabular-nums text-ink-muted" dateTime={command.sent_at}>{clockTime(command.sent_at)}</time>
              <div className="grid min-w-0 gap-0.5">
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className="flex-none font-medium text-ink">{commandSender(command)}</span>
                  {mark ? <span className={cx("flex-none text-caption", mark.tone)}>{mark.label}</span> : null}
                  {report ? <span className={cx("flex-none text-caption", report.tone)}>{report.label}</span> : null}
                </span>
                <span className={cx("min-w-0 whitespace-pre-wrap break-words text-ink-secondary", command.kind === "keys" && "font-mono text-caption")}>{command.content}</span>
                {command.error ? <span className="min-w-0 break-words text-caption text-ink-muted">{command.error}</span> : null}
                {report && command.report_error ? <span className="min-w-0 break-words text-caption text-ink-muted">{command.report_error}</span> : null}
              </div>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}
