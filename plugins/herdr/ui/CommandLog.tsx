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
          return (
            <li key={command.id} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3">
              <time className="text-caption tabular-nums text-ink-muted" dateTime={command.sent_at}>{clockTime(command.sent_at)}</time>
              <div className="grid min-w-0 gap-0.5">
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className="flex-none font-medium text-ink">{commandSender(command)}</span>
                  {mark ? <span className={cx("flex-none text-caption", mark.tone)}>{mark.label}</span> : null}
                </span>
                <span className={cx("min-w-0 whitespace-pre-wrap break-words text-ink-secondary", command.kind === "keys" && "font-mono text-caption")}>{command.content}</span>
                {command.error ? <span className="min-w-0 break-words text-caption text-ink-muted">{command.error}</span> : null}
              </div>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}
