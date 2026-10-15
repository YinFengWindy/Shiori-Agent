import { LinkBreak } from "@phosphor-icons/react";
import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { EmptyState } from "./EmptyState";
import { TaskDetailView } from "./TaskDetailView";
import { AgentStatusLabel } from "./TaskStatus";
import { TaskTerminal } from "./TaskTerminal";
import { agentKindLabel, agentTitle } from "./agentSelectors";
import { disconnectedMessage } from "./taskFeed";
import { useAgentDetail } from "./useAgentDetail";
import type { AgentSummary } from "./types";

/**
 * The selected agent: its terminal, polled while shown. An agent carrying a
 * plugin task shows the task's delivery and actions around that terminal; an
 * agent Herdr no longer lists or knows says so instead of going blank.
 */
export function AgentDetailView({ paneId, listed, listLoaded, listError, roleName, tasksConnected, pollMs, client, host }: {
  paneId: string;
  /** The agent as the latest list shows it; undefined once it left the list. */
  listed: AgentSummary | undefined;
  listLoaded: boolean;
  /** Already shown by the page; the detail does not repeat it. */
  listError: string;
  /** The originating role of the agent's plugin task. */
  roleName: (taskId: string) => string;
  /** Task actions follow the task feeds' connection. */
  tasksConnected: boolean;
  pollMs: number;
  client: PluginRpcClient;
  host: PluginHostServices;
}) {
  const detail = useAgentDetail(client, host, paneId, pollMs);
  const gone = (listLoaded && !listed) || detail.value?.agent === null;
  if (gone) {
    return (
      <div className="grid min-h-0 flex-1 place-items-center" role="status">
        <EmptyState icon={LinkBreak} label="Agent 已不存在" />
      </div>
    );
  }
  const agent = detail.value?.agent ?? listed;
  const readError = detail.error && detail.error !== disconnectedMessage && detail.error !== listError ? detail.error : "";
  if (!agent) {
    return readError ? <host.ui.InlineError title="Agent 读取失败" message={readError} layout="card" className="m-6" /> : null;
  }
  const output = detail.value?.agent ? detail.value.output : undefined;
  if (agent.task_id) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {readError ? <host.ui.InlineError title="Agent 读取失败" message={readError} layout="strip" /> : null}
        <TaskDetailView
          key={agent.task_id}
          taskId={agent.task_id}
          roleName={roleName(agent.task_id)}
          output={output}
          listConnected={tasksConnected}
          client={client}
          host={host}
        />
      </div>
    );
  }
  return (
    <article className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)]" aria-label="Agent 详情">
      <header className="grid gap-1 border-b border-line-soft px-6 pb-4 pt-5">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="min-w-0 break-words font-display text-title text-ink">{agentTitle(agent)}</h1>
          <AgentStatusLabel status={agent.status} className="text-body-sm text-ink-secondary" />
        </div>
        <p className="min-w-0 truncate text-body-sm text-ink-muted" title={agent.cwd}>
          {agentKindLabel(agent.agent)} · {agent.cwd}
        </p>
      </header>
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-6 py-4">
        {readError ? <host.ui.InlineError title="Agent 读取失败" message={readError} layout="row" /> : null}
        <TaskTerminal output={output ?? ""} />
      </div>
    </article>
  );
}
