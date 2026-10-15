import { AgentStatusLabel } from "./AgentStatusLabel";
import { agentKindLabel, agentTitle } from "./agentSelectors";
import type { AgentSummary } from "./types";

/**
 * The selected agent as Herdr reports it: terminal title, Herdr state, kind
 * and working directory. Above a plugin task the task's title is the page
 * heading, so the agent's title is not one there.
 */
export function AgentHeader({ agent, primary }: { agent: AgentSummary; primary: boolean }) {
  const title = agentTitle(agent);
  return (
    <header className="grid gap-1 border-b border-line-soft px-6 pb-4 pt-5" aria-label="Agent">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        {primary ? (
          <h1 className="min-w-0 break-words font-display text-title text-ink">{title}</h1>
        ) : (
          <p className="min-w-0 truncate text-body font-semibold text-ink">{title}</p>
        )}
        <AgentStatusLabel status={agent.status} className="text-body-sm text-ink-secondary" />
      </div>
      <p className="min-w-0 truncate text-body-sm text-ink-muted" title={agent.cwd}>
        {agentKindLabel(agent.agent)} · {agent.cwd}
      </p>
    </header>
  );
}
