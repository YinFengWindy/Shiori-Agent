import { TerminalWindow } from "@phosphor-icons/react";
import { cx } from "@yinfengwindy/shiori-sdk";
import { listItemClass } from "./TaskListItem";
import { ToneDot } from "./TaskStatus";
import { agentKindLabel, agentStatusLabel, agentStatusTone, agentTitle } from "./agentSelectors";
import type { AgentSummary } from "./types";

/** One agent of the session without a plugin task: terminal title, kind and Herdr state. */
export function AgentListItem({ agent, selected, onSelect }: {
  agent: AgentSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={cx(listItemClass, selected && "bg-surface text-ink shadow-soft")}
      aria-current={selected ? "true" : undefined}
      title={agent.cwd || undefined}
      onClick={onSelect}
    >
      <span className="grid h-8 w-8 place-items-center rounded-full bg-accent-softer text-accent" aria-hidden="true">
        <TerminalWindow className="h-4 w-4" />
      </span>
      <span className="grid min-w-0 gap-1">
        <span className="min-w-0 truncate font-semibold leading-tight">{agentTitle(agent)}</span>
        <span className="flex min-w-0 items-center gap-1.5 text-caption leading-tight text-ink-muted">
          <ToneDot tone={agentStatusTone(agent.status)} />
          <span className="truncate">{agentKindLabel(agent.agent)} · {agentStatusLabel(agent.status)}</span>
        </span>
      </span>
    </button>
  );
}
