import { CursorClick, TerminalWindow } from "@phosphor-icons/react";
import type { PluginNavPageComponentProps } from "@yinfengwindy/shiori-sdk";
import { EmptyState } from "./EmptyState";
import { TaskDetailView } from "./TaskDetailView";
import { useDashboard } from "./dashboardStore";

/** Herdr's page: connection state, the empty states, or the task selected in the sidebar. */
export function DashboardPage({ client, host }: PluginNavPageComponentProps) {
  const { state } = useDashboard(client, host);
  const { list } = state;
  const tasks = list.value?.tasks;
  const selected = tasks?.find((task) => task.id === state.selectedId);
  const role = selected ? state.roles.find((item) => item.id === selected.role_id) : undefined;
  return (
    // A flex column: the detail takes the remaining height whether or not an error strip is shown.
    <div className="flex h-full min-h-0 flex-col" data-testid="herdr-page">
      {list.error ? <host.ui.InlineError title="任务连接不可用" message={list.error} layout="strip" /> : null}
      {state.rolesError ? <host.ui.InlineError title="角色读取失败" message={state.rolesError} layout="strip" /> : null}
      {selected ? (
        <TaskDetailView
          key={selected.id}
          taskId={selected.id}
          roleName={role?.name ?? selected.role_id}
          listConnected={list.connected}
          client={client}
          host={host}
        />
      ) : tasks ? (
        <div className="grid min-h-0 flex-1 place-items-center">
          <EmptyState icon={tasks.length ? CursorClick : TerminalWindow} label={tasks.length ? "未选择任务" : "暂无任务"} />
        </div>
      ) : null}
    </div>
  );
}
