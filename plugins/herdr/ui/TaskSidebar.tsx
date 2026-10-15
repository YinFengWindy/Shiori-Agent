import { useEffect, useState } from "react";
import { TerminalWindow } from "@phosphor-icons/react";
import {
  cx,
  secondarySidebarSurfaceClass,
  SidebarResizeHandle,
  sidebarContentMotionClass,
  type PluginNavPageSidebarComponentProps,
  type PluginHostServices,
  type RoleRecord,
} from "@yinfengwindy/shiori-sdk";
import { EmptyState } from "./EmptyState";
import { TaskListItem } from "./TaskListItem";
import { useDashboard } from "./dashboardStore";
import { groupTasks } from "./taskSelectors";
import type { TaskSummary } from "./types";

/** Relative times in the list only change by the minute. */
function useMinuteClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function TaskGroup({ label, tasks, ...item }: {
  label: string;
  tasks: readonly TaskSummary[];
  roles: ReadonlyMap<string, RoleRecord>;
  selectedId: string | null;
  now: Date;
  host: PluginHostServices;
  onSelect: (taskId: string) => void;
}) {
  if (!tasks.length) return null;
  return (
    <section className="grid gap-1.5" aria-label={label}>
      <h2 className="px-2 text-caption font-medium text-ink-muted">{label}</h2>
      {tasks.map((task) => (
        <TaskListItem
          key={task.id}
          task={task}
          role={item.roles.get(task.role_id)}
          selected={task.id === item.selectedId}
          now={item.now}
          host={item.host}
          onSelect={item.onSelect}
        />
      ))}
    </section>
  );
}

/** Herdr's secondary sidebar: every role's tasks, split into 进行中 / 已结束. */
export function TaskSidebar({ client, host, animating, collapsed, width, onBeginResize, onNavigate }: PluginNavPageSidebarComponentProps) {
  const { state, store } = useDashboard(client, host);
  const now = useMinuteClock();
  const tasks = state.list.value?.tasks;
  const groups = groupTasks(tasks ?? []);
  const roles = new Map(state.roles.map((role) => [role.id, role]));
  const select = (taskId: string) => {
    store.select(taskId);
    // Selecting is invisible to the host; let it close a compact overlay drawer.
    onNavigate?.();
  };
  const item = { roles, selectedId: state.selectedId, now, host, onSelect: select };
  return (
    <aside
      className={cx(
        "relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] overflow-hidden py-[18px]",
        secondarySidebarSurfaceClass,
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[18px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <nav className="scrollbar-stable grid min-h-0 content-start gap-4 overflow-y-auto overflow-x-hidden" aria-label="Herdr 任务">
        {tasks && !tasks.length ? <EmptyState icon={TerminalWindow} label="暂无任务" /> : null}
        <TaskGroup label="进行中" tasks={groups.active} {...item} />
        <TaskGroup label="已结束" tasks={groups.finished} {...item} />
      </nav>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
