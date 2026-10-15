import { FileX, TerminalWindow } from "@phosphor-icons/react";
import type { PluginNavPageComponentProps } from "@yinfengwindy/shiori-sdk";
import { AgentDetailView } from "./AgentDetailView";
import { EmptyState } from "./EmptyState";
import { TaskDetailView } from "./TaskDetailView";
import { resolveSelection } from "./agentSelectors";
import { useDashboard } from "./dashboardStore";

/** Herdr's page: connection and session state, then the agent or task selected in the sidebar. */
export function DashboardPage({ client, host }: PluginNavPageComponentProps) {
  const { state, store } = useDashboard(client, host);
  const { list, agents } = state;
  const tasks = list.value?.tasks ?? [];
  const current = resolveSelection(state.selection, agents.value, tasks);
  const roleName = (taskId: string) => {
    const roleId = tasks.find((task) => task.id === taskId)?.role_id ?? "";
    return state.roles.find((role) => role.id === roleId)?.name ?? roleId;
  };
  // A lost bridge fails both feeds with the same message; report it once.
  const agentsError = agents.error !== list.error ? agents.error : "";
  const settled = list.value !== null && (agents.value !== null || agents.error !== "");
  return (
    // A flex column: the detail takes the remaining height whether or not an error strip is shown.
    <div className="flex h-full min-h-0 flex-col" data-testid="herdr-page">
      {list.error ? <host.ui.InlineError title="任务连接不可用" message={list.error} layout="strip" /> : null}
      {agentsError ? <host.ui.InlineError title="Herdr session 不可用" message={agentsError} layout="strip" /> : null}
      {state.rolesError ? <host.ui.InlineError title="角色读取失败" message={state.rolesError} layout="strip" /> : null}
      {current?.kind === "agent" ? (
        <AgentDetailView
          key={current.paneId}
          paneId={current.paneId}
          listed={current.agent}
          listLoaded={agents.value !== null}
          listError={agents.error}
          roleName={roleName}
          tasksConnected={list.connected}
          pollMs={store.pollMs}
          client={client}
          host={host}
        />
      ) : current?.kind === "task" && current.task ? (
        <TaskDetailView
          key={current.taskId}
          taskId={current.taskId}
          roleName={roleName(current.taskId)}
          listConnected={list.connected}
          client={client}
          host={host}
        />
      ) : current || settled ? (
        <div className="grid min-h-0 flex-1 place-items-center">
          {current ? <EmptyState icon={FileX} label="任务已不存在" /> : <EmptyState icon={TerminalWindow} label="暂无 Agent" />}
        </div>
      ) : null}
    </div>
  );
}
