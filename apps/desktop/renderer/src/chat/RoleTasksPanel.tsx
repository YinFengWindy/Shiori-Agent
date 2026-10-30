import { useState } from "react";
import type { RoleTask } from "../shared/types";
import { useRoleTasksContribution } from "../plugins/roleTasksUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { RoleTaskDetails } from "./RoleTaskDetails";
import { RoleTaskList } from "./RoleTaskList";
import { blockPanelView, reconcileRoleTaskPanelView, type RoleTaskPanelView } from "./roleTaskPanelState";

export { groupRoleTasks } from "./roleTaskPanelState";

/**
 * Renders the role's task list and a host task's details, and hands the whole
 * panel to the plugin block (`roleTasks`) while one of its views is open.
 */
export function RoleTasksPanel({ roleId, tasks, cancellingTaskId, error, onClearError, onCancel }: {
  /** The open role; the caller keys the panel by it. */
  roleId: string;
  tasks: RoleTask[];
  cancellingTaskId: string;
  error: string;
  onClearError: () => void;
  onCancel: (taskId: string) => Promise<void>;
}) {
  const [requestedView, setRequestedView] = useState<RoleTaskPanelView>({ kind: "list" });
  const [confirmingCancelTaskId, setConfirmingCancelTaskId] = useState("");
  const contributed = useRoleTasksContribution();
  const pluginEnabled = usePluginEnabledState();
  // The scheduled-task block is the plugin's own; the panel only mounts it while the plugin is on.
  const Block = contributed && pluginEnabled(contributed.pluginId) && roleId ? contributed.Component : null;
  const view = reconcileRoleTaskPanelView(requestedView, tasks);

  const navigate = (next: RoleTaskPanelView) => {
    onClearError();
    setConfirmingCancelTaskId("");
    setRequestedView(next);
  };
  const showBlockView = (blockView: string) => navigate(blockPanelView(blockView));

  if (view.kind === "block" && Block) {
    return <Block roleId={roleId} view={view.blockView} onViewChange={showBlockView} />;
  }

  const selectedTask = view.kind === "detail" ? tasks.find((task) => task.id === view.taskId) : undefined;
  if (selectedTask) {
    return (
      <RoleTaskDetails
        task={selectedTask}
        cancelling={cancellingTaskId === selectedTask.id}
        error={error}
        confirmingCancel={confirmingCancelTaskId === selectedTask.id}
        onBack={() => navigate({ kind: "list" })}
        onBeginCancel={() => setConfirmingCancelTaskId(selectedTask.id)}
        onDismissCancel={() => setConfirmingCancelTaskId("")}
        onCancel={() => {
          void onCancel(selectedTask.id)
            .then(() => navigate({ kind: "list" }))
            .catch(() => undefined);
        }}
      />
    );
  }

  return (
    <RoleTaskList
      tasks={tasks}
      block={Block ? <Block roleId={roleId} view="" onViewChange={showBlockView} /> : null}
      onSelect={(taskId) => navigate({ kind: "detail", taskId })}
    />
  );
}
