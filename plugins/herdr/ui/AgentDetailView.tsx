import { LinkBreak } from "@phosphor-icons/react";
import type { PluginHostServices, PluginRpcClient, RoleRecord } from "@yinfengwindy/shiori-sdk";
import { AgentComposer, type DirectControl } from "./AgentComposer";
import { AgentHandlerLine } from "./AgentHandlerLine";
import { AgentHeader } from "./AgentHeader";
import { CommandLog } from "./CommandLog";
import { EmptyState } from "./EmptyState";
import { TaskDetailView } from "./TaskDetailView";
import { TaskTerminal } from "./TaskTerminal";
import { disconnectedMessage } from "./taskFeed";
import { useAgentDetail } from "./useAgentDetail";
import type { AgentSummary } from "./types";

/**
 * The selected agent: its Herdr header, terminal and command record, polled
 * while shown, with the input that sends to it. An agent carrying a plugin
 * task shows the task's delivery and actions around that terminal, and takes
 * direct input only while no run of the task owns it; an agent Herdr no
 * longer lists or knows says so instead of going blank.
 */
export function AgentDetailView({ paneId, listed, listLoaded, listError, roleName, findRole, tasksConnected, pollMs, client, host }: {
  paneId: string;
  /** The agent as the latest list shows it; undefined once it left the list. */
  listed: AgentSummary | undefined;
  listLoaded: boolean;
  /** Already shown by the page; the detail does not repeat it. */
  listError: string;
  /** The originating role of the agent's plugin task. */
  roleName: (taskId: string) => string;
  /** A role of the host by ID, for the agent's handling role. */
  findRole: (roleId: string) => RoleRecord | undefined;
  /** Task actions follow the task feeds' connection. */
  tasksConnected: boolean;
  pollMs: number;
  client: PluginRpcClient;
  host: PluginHostServices;
}) {
  const { state: detail, refresh } = useAgentDetail(client, host, paneId, pollMs);
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
  const failure = readError ? <host.ui.InlineError title="Agent 读取失败" message={readError} layout={agent ? "strip" : "card"} className={agent ? undefined : "m-6"} /> : null;
  if (!agent) return failure;
  const output = detail.value?.agent ? detail.value.output : undefined;
  const commands = detail.value?.commands ?? [];
  // Sending needs a live bridge and a session the last reads reached.
  const reachable = detail.connected && !detail.error && !listError;
  const direct: DirectControl = { paneId, enabled: reachable && detail.value?.can_prompt === true, onSent: () => { void refresh(); } };
  return (
    <article className="flex min-h-0 flex-1 flex-col" aria-label="Agent 详情">
      {failure}
      <AgentHeader agent={agent} primary={!agent.task_id}>
        {detail.value?.agent ? <AgentHandlerLine handler={detail.value.handler} findRole={findRole} host={host} /> : null}
      </AgentHeader>
      {agent.task_id ? (
        <TaskDetailView
          key={agent.task_id}
          taskId={agent.task_id}
          roleName={roleName(agent.task_id)}
          output={output}
          commands={commands}
          direct={detail.value?.can_prompt ? direct : undefined}
          listConnected={tasksConnected}
          client={client}
          host={host}
        />
      ) : (
        <>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-4">
            <TaskTerminal output={output ?? ""} />
            <CommandLog commands={commands} />
          </div>
          <AgentComposer direct={direct} client={client} host={host} />
        </>
      )}
    </article>
  );
}
