import { Plus } from "@phosphor-icons/react";
import type { RoleTask } from "../shared/types";
import { groupRoleTasks, taskKindLabels } from "./roleTaskPanelState";

/** Renders the compact role-task directory. */
export function RoleTaskList({ tasks, onCreate, onSelect }: {
  tasks: RoleTask[];
  onCreate: () => void;
  onSelect: (taskId: string) => void;
}) {
  const groups = groupRoleTasks(tasks);
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] rounded-[20px] bg-[#F1F5F9] p-4 text-sm text-[#334155]">
      <div className="flex items-center justify-between px-1 pb-3">
        <span className="font-semibold text-[#272536]">任务</span>
        <button
          className="grid h-8 w-8 place-items-center rounded-md text-[#5B6472] transition hover:bg-white hover:text-[#272536]"
          type="button"
          aria-label="新增计划任务"
          onClick={onCreate}
        >
          <Plus className="h-4 w-4" weight="bold" />
        </button>
      </div>
      <div className="min-h-0 overflow-y-auto rounded-[16px] bg-white/90 p-3">
        {groups.length ? groups.map((group) => (
          <section key={group.kind} className="mb-4 last:mb-0">
            <div className="px-1 pb-1 text-[11px] font-medium tracking-wide text-[#98A2B3]">{taskKindLabels[group.kind]}</div>
            {group.tasks.length ? group.tasks.map((task) => (
              <button
                key={`${task.kind}:${task.id}`}
                className="block w-full border-b border-[#E6EBF2] px-1 py-3 text-left transition last:border-b-0 hover:bg-[#F8FAFC]"
                type="button"
                onClick={() => onSelect(task.id)}
              >
                <div className="truncate font-semibold">{task.label}</div>
                <div className="mt-1 truncate text-xs text-[#667085]">{task.detail || "—"}</div>
              </button>
            )) : <div className="px-1 py-2 text-xs text-[#98A2B3]">暂无任务</div>}
          </section>
        )) : <div className="grid h-full place-items-center text-xs text-[#98A2B3]">暂无任务</div>}
      </div>
    </div>
  );
}
