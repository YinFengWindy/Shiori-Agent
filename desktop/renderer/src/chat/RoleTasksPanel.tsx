import type { RoleTask, RoleTaskKind } from "../shared/types";
import { formatTimestamp } from "../shared/format";

const taskKindLabels: Record<RoleTaskKind, string> = {
  schedule: "计划任务",
  subagent: "后台任务",
  memory_maintenance: "记忆维护",
};

const taskStatusLabels: Record<string, string> = {
  running: "进行中",
  scheduled: "待执行",
};

/** Groups role tasks in the stable order used by the task sidebar. */
export function groupRoleTasks(tasks: RoleTask[]): Array<{ kind: RoleTaskKind; tasks: RoleTask[] }> {
  return (["schedule", "subagent", "memory_maintenance"] as const)
    .map((kind) => ({ kind, tasks: tasks.filter((task) => task.kind === kind) }))
    .filter((group) => group.tasks.length > 0);
}

/** Renders the role-scoped task list in the chat sidebar. */
export function RoleTasksPanel({ tasks, cancellingTaskId, onCancel }: {
  tasks: RoleTask[];
  cancellingTaskId: string;
  onCancel: (taskId: string) => void;
}) {
  const groups = groupRoleTasks(tasks);
  return (
    <div className="grid h-full min-h-0 rounded-[20px] bg-[#F1F5F9] p-4 text-sm text-[#334155]">
      <div className="min-h-0 overflow-y-auto rounded-[16px] bg-white/90 p-3">
        {groups.length ? groups.map((group) => (
          <section key={group.kind} className="mb-4 last:mb-0">
            <div className="px-1 pb-1 text-[11px] font-medium tracking-wide text-[#98A2B3]">{taskKindLabels[group.kind]}</div>
            {group.tasks.map((task) => (
              <div key={`${task.kind}:${task.id}`} className="border-b border-[#E6EBF2] py-3 last:border-b-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{task.label}</span>
                  <span className="text-xs text-[#7A8593]">{taskStatusLabels[task.status] ?? task.status}</span>
                </div>
                {task.detail ? <div className="mt-1 text-xs text-[#667085]">{task.detail}</div> : null}
                {task.next_run_at ? <div className="mt-1 text-xs text-[#98A2B3]">{formatTimestamp(task.next_run_at)}</div> : null}
                {task.cancellable ? (
                  <button
                    className="mt-2 rounded-md border border-[#D8DFE7] px-2 py-1 text-xs transition hover:border-[#B8C2CE] disabled:cursor-default disabled:opacity-50"
                    type="button"
                    disabled={cancellingTaskId === task.id}
                    onClick={() => onCancel(task.id)}
                  >取消</button>
                ) : null}
              </div>
            ))}
          </section>
        )) : <div className="grid h-full place-items-center text-xs text-[#98A2B3]">当前角色没有后台任务</div>}
      </div>
    </div>
  );
}
