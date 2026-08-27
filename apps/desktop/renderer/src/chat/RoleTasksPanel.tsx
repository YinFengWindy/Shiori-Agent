import { useEffect, useState } from "react";
import type { RoleTask, ScheduleTaskFormData } from "../shared/types";
import { RoleTaskDetails } from "./RoleTaskDetails";
import { RoleTaskForm } from "./RoleTaskForm";
import { RoleTaskList } from "./RoleTaskList";
import { createScheduleTaskFormData, scheduleTaskFormDataFromTask } from "./roleTaskFormState";
import {
  reconcileRoleTaskPanelView,
  reduceRoleTaskPanelView,
  type RoleTaskPanelAction,
  type RoleTaskPanelView,
} from "./roleTaskPanelState";

export { groupRoleTasks } from "./roleTaskPanelState";

/** Renders and coordinates list, detail, create, and edit task views. */
export function RoleTasksPanel({ tasks, operation, error, onClearError, onCreate, onUpdate, onCancel }: {
  tasks: RoleTask[];
  operation: { kind: "create" | "update" | "cancel"; taskId: string } | null;
  error: string;
  onClearError: () => void;
  onCreate: (data: ScheduleTaskFormData) => Promise<RoleTask>;
  onUpdate: (taskId: string, data: ScheduleTaskFormData) => Promise<RoleTask>;
  onCancel: (taskId: string) => Promise<void>;
}) {
  const [view, setView] = useState<RoleTaskPanelView>({ kind: "list" });
  const [confirmingCancelTaskId, setConfirmingCancelTaskId] = useState("");
  const selectedTask = view.kind === "detail" || view.kind === "edit"
    ? tasks.find((task) => task.id === view.taskId)
    : undefined;

  useEffect(() => {
    setView((current) => reconcileRoleTaskPanelView(current, tasks));
  }, [tasks]);

  const navigate = (action: RoleTaskPanelAction) => {
    onClearError();
    setConfirmingCancelTaskId("");
    setView((current) => reduceRoleTaskPanelView(current, action));
  };

  if (view.kind === "create") {
    return (
      <RoleTaskForm
        title="新增计划任务"
        initialData={createScheduleTaskFormData()}
        saving={operation?.kind === "create"}
        error={error}
        onBack={() => navigate({ type: "show-list" })}
        onSave={async (data) => {
          const task = await onCreate(data);
          navigate({ type: "show-detail", taskId: task.id });
        }}
      />
    );
  }

  if (view.kind === "edit" && selectedTask) {
    return (
      <RoleTaskForm
        title="编辑计划任务"
        initialData={scheduleTaskFormDataFromTask(selectedTask)}
        saving={operation?.kind === "update" && operation.taskId === selectedTask.id}
        error={error}
        onBack={() => navigate({ type: "show-detail", taskId: selectedTask.id })}
        onSave={async (data) => {
          await onUpdate(selectedTask.id, data);
          navigate({ type: "show-detail", taskId: selectedTask.id });
        }}
      />
    );
  }

  if (view.kind === "detail" && selectedTask) {
    const cancelling = operation?.kind === "cancel" && operation.taskId === selectedTask.id;
    return (
      <RoleTaskDetails
        task={selectedTask}
        cancelling={cancelling}
        error={error}
        confirmingCancel={confirmingCancelTaskId === selectedTask.id}
        onBack={() => navigate({ type: "show-list" })}
        onEdit={() => navigate({ type: "show-edit", taskId: selectedTask.id })}
        onBeginCancel={() => setConfirmingCancelTaskId(selectedTask.id)}
        onDismissCancel={() => setConfirmingCancelTaskId("")}
        onCancel={() => {
          void onCancel(selectedTask.id)
            .then(() => navigate({ type: "show-list" }))
            .catch(() => undefined);
        }}
      />
    );
  }

  return (
    <RoleTaskList
      tasks={tasks}
      onCreate={() => navigate({ type: "show-create" })}
      onSelect={(taskId) => navigate({ type: "show-detail", taskId })}
    />
  );
}
