import { useEffect, useState, type ReactNode } from "react";
import { TerminalWindow } from "@phosphor-icons/react";
import {
  cx,
  secondarySidebarShellClass,
  SidebarResizeHandle,
  type PluginNavPageSidebarComponentProps,
} from "@yinfengwindy/shiori-sdk";
import { AgentListItem } from "./AgentListItem";
import { EmptyState } from "./EmptyState";
import { TaskListItem } from "./TaskListItem";
import { resolveSelection, unlinkedTasks, type Selection } from "./agentSelectors";
import { useDashboard } from "./dashboardStore";

/** Relative times in the list only change by the minute. */
function useMinuteClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="grid gap-1.5" aria-label={label}>
      <h2 className="truncate px-2 text-caption font-medium text-ink-muted">{label}</h2>
      {children}
    </section>
  );
}

/**
 * Herdr's secondary sidebar: the session's agents grouped by workspace, an
 * agent carrying a plugin task shown as that task, then the plugin tasks no
 * listed agent carries.
 */
export function AgentSidebar({ client, host, animating, collapsed, width, onBeginResize, onNavigate }: PluginNavPageSidebarComponentProps) {
  const { state, store } = useDashboard(client, host);
  const now = useMinuteClock();
  const agents = state.agents.value;
  const tasks = state.list.value?.tasks ?? [];
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const roles = new Map(state.roles.map((role) => [role.id, role]));
  const others = unlinkedTasks(tasks, agents);
  const current = resolveSelection(state.selection, agents, tasks);
  const select = (selection: Selection) => {
    store.select(selection);
    // Selecting is invisible to the host; let it close a compact overlay drawer.
    onNavigate?.();
  };
  const empty = agents !== null && state.list.value !== null && !agents.workspaces.length && !others.length;
  return (
    <aside
      className={cx("grid grid-rows-[minmax(0,1fr)] overflow-hidden", secondarySidebarShellClass({ animating, collapsed, inset: "list" }))}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <nav className="scrollbar-stable grid min-h-0 content-start gap-4 overflow-y-auto overflow-x-hidden" aria-label="Herdr Agent">
        {empty ? <EmptyState icon={TerminalWindow} label="暂无 Agent" /> : null}
        {agents?.workspaces.map((workspace) => (
          <Group key={workspace.workspace_id} label={workspace.label}>
            {workspace.agents.map((agent) => {
              const task = agent.task_id ? taskById.get(agent.task_id) : undefined;
              const selected = current?.kind === "agent" && current.paneId === agent.pane_id;
              const onSelect = () => select({ kind: "agent", paneId: agent.pane_id });
              return task ? (
                <TaskListItem key={agent.pane_id} task={task} role={roles.get(task.role_id)} selected={selected} now={now} host={host} onSelect={onSelect} />
              ) : (
                <AgentListItem key={agent.pane_id} agent={agent} selected={selected} onSelect={onSelect} />
              );
            })}
          </Group>
        ))}
        {others.length ? (
          <Group label="插件任务">
            {others.map((task) => (
              <TaskListItem
                key={task.id}
                task={task}
                role={roles.get(task.role_id)}
                selected={current?.kind === "task" && current.taskId === task.id}
                now={now}
                host={host}
                onSelect={() => select({ kind: "task", taskId: task.id })}
              />
            ))}
          </Group>
        ) : null}
      </nav>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
