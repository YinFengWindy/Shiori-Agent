import { useState } from "react";
import { ArrowsClockwise, TerminalWindow, SlidersHorizontal } from "@phosphor-icons/react";
import { cardClass, compactGhostButtonClass, cx, Select, settingsInputClass, type PluginNavPageComponentProps } from "@yinfengwindy/shiori-sdk";
import { TaskDetail } from "./TaskDetail";
import { TaskList } from "./TaskList";
import { filterTasks, repositoryName, statusLabels, type TaskFilters } from "./selectors";
import { useDashboard, useRoleNames } from "./useDashboard";

/** The page only assembles the shared read model, selection, filters and detail view. */
export function DashboardPage({ client, host }: PluginNavPageComponentProps) {
  const { state, store } = useDashboard(client, host);
  const { names, error: roleError } = useRoleNames(host);
  const [filters, setFilters] = useState<TaskFilters>({ role: "", repository: "", status: "" });
  const [selectedId, setSelectedId] = useState("");
  const visible = filterTasks(state.tasks, filters);
  const selected = visible.find((task) => task.id === selectedId) ?? visible[0];
  const roleIds = [...new Set(state.tasks.map((task) => task.role_id))];
  const repositories = [...new Set(state.tasks.map((task) => task.repository))];
  const running = state.tasks.filter((task) => ["queued", "preparing", "running", "cancelling"].includes(task.status)).length;
  return <main className="herdr-dashboard flex h-full min-h-0 flex-col gap-5 p-5 text-ink">
    <header className="flex flex-wrap items-center justify-between gap-4"><div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-lg bg-accent-soft text-accent-text"><TerminalWindow className="h-5 w-5" aria-hidden="true" /></div><div><h1 className="font-display text-headline">Herdr</h1><p className="text-caption text-ink-muted">{state.tasks.length} 个任务 · {running} 个进行中</p></div></div>
      <button type="button" className={compactGhostButtonClass} onClick={() => { void store.refresh(); }} disabled={state.loading}><ArrowsClockwise className="h-4 w-4" aria-hidden="true" />刷新</button>
    </header>
    {state.error ? <host.ui.InlineError title="任务连接不可用" message={state.error} actions={<button type="button" className={compactGhostButtonClass} onClick={() => { store.stop(); void store.start(); }}>重新连接</button>} /> : null}
    {roleError ? <host.ui.InlineError title="角色名称加载失败" message={roleError} persona={false} /> : null}
    <div className="herdr-filters flex flex-wrap items-center gap-3" role="group" aria-label="筛选任务"><SlidersHorizontal className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
      <Select aria-label="按角色筛选" className={cx(settingsInputClass, "herdr-filter")} value={filters.role} options={[{ value: "", label: "全部角色" }, ...roleIds.map((id) => ({ value: id, label: names.get(id) ?? id }))]} onValueChange={(role) => setFilters((value) => ({ ...value, role }))} />
      <Select aria-label="按仓库筛选" className={cx(settingsInputClass, "herdr-filter")} value={filters.repository} options={[{ value: "", label: "全部仓库" }, ...repositories.map((path) => ({ value: path, label: path, triggerLabel: repositoryName(path) }))]} onValueChange={(repository) => setFilters((value) => ({ ...value, repository }))} />
      <Select aria-label="按状态筛选" className={cx(settingsInputClass, "herdr-filter")} value={filters.status} options={[{ value: "", label: "全部状态" }, ...Object.entries(statusLabels).map(([value, label]) => ({ value, label }))]} onValueChange={(status) => setFilters((value) => ({ ...value, status }))} />
    </div>
    {state.loading ? <div role="status" className={cx(cardClass, "grid flex-1 place-items-center p-10 text-body text-ink-muted")}>正在加载任务…</div> : state.tasks.length === 0 ? <div className={cx(cardClass, "grid flex-1 place-items-center p-10 text-body text-ink-muted")}>暂无任务</div> : <div className={cx(cardClass, "herdr-workspace grid min-h-0 flex-1 overflow-hidden")}>
      <TaskList tasks={visible} selectedId={selected?.id ?? ""} names={names} onSelect={setSelectedId} />
      {selected ? <TaskDetail key={selected.id} task={selected} roleName={names.get(selected.role_id) ?? selected.role_id} client={client} host={host} connected={state.connected} refresh={store.refresh} /> : <div className="grid place-items-center p-10 text-body text-ink-muted">选择一个任务</div>}
    </div>}
  </main>;
}
