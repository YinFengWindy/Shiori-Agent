import type { PluginRoleTasksComponentProps } from "@yinfengwindy/shiori-sdk";
import { formatBlockView, parseBlockView, reconcileBlockView, type ScheduleBlockView } from "./blockView";
import { ScheduleTaskDetails } from "./ScheduleTaskDetails";
import { ScheduleTaskForm } from "./ScheduleTaskForm";
import { ScheduleTaskGroup } from "./ScheduleTaskGroup";
import { createScheduleTaskFormData, scheduleTaskFormDataFromTask } from "./scheduleTaskFormState";
import { useScheduledTasks } from "./useScheduledTasks";

/**
 * The `roleTasks` block: the role's scheduled tasks as a group of the task
 * list, and their detail, create and edit views, which fill the panel.
 */
export function ScheduleTasksBlock({ roleId, view, onViewChange, client, host }: PluginRoleTasksComponentProps) {
  const requested = parseBlockView(view);
  const scheduled = useScheduledTasks(client, host, roleId, {
    openTaskId: requested.kind === "detail" || requested.kind === "edit" ? requested.taskId : "",
    // The read that no longer has the open job hands the panel back in the same update.
    onOpenTaskGone: () => onViewChange(""),
  });
  const { tasks, operation, error } = scheduled;
  const current = reconcileBlockView(requested, tasks);
  const show = (next: ScheduleBlockView) => {
    scheduled.clearError();
    onViewChange(formatBlockView(next));
  };

  if (current.kind === "create") {
    return (
      <ScheduleTaskForm
        title="新增计划任务"
        initialData={createScheduleTaskFormData()}
        saving={operation?.kind === "create"}
        error={error}
        host={host}
        onBack={() => show({ kind: "list" })}
        onSave={async (data) => {
          const task = await scheduled.create(data);
          show({ kind: "detail", taskId: task.id });
        }}
      />
    );
  }

  const selected = current.kind === "list" ? undefined : tasks?.find((task) => task.id === current.taskId);
  if (current.kind === "edit" && selected) {
    return (
      <ScheduleTaskForm
        title="编辑计划任务"
        initialData={scheduleTaskFormDataFromTask(selected)}
        saving={operation?.kind === "update"}
        error={error}
        host={host}
        onBack={() => show({ kind: "detail", taskId: selected.id })}
        onSave={async (data) => {
          await scheduled.update(selected.id, data);
          show({ kind: "detail", taskId: selected.id });
        }}
      />
    );
  }

  if (current.kind === "detail" && selected) {
    return (
      <ScheduleTaskDetails
        task={selected}
        cancelling={operation?.kind === "cancel"}
        error={error}
        host={host}
        onBack={() => show({ kind: "list" })}
        onEdit={() => show({ kind: "edit", taskId: selected.id })}
        onCancel={async () => {
          await scheduled.cancel(selected.id);
          show({ kind: "list" });
        }}
      />
    );
  }

  // A view opened before the first read waits for it. A job missing from
  // the last read was already reported through `onOpenTaskGone`.
  if (current.kind !== "list" || view) return null;
  return (
    <ScheduleTaskGroup
      tasks={tasks ?? []}
      error={error}
      host={host}
      onCreate={() => show({ kind: "create" })}
      onSelect={(taskId) => show({ kind: "detail", taskId })}
    />
  );
}
