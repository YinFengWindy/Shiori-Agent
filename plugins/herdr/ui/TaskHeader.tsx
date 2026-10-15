import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { CancelTaskButton, OpenPullRequestButton } from "./TaskActions";
import { StatusLabel } from "./TaskStatus";
import { agentLabel, repositoryName, taskTitle } from "./taskSelectors";
import type { TaskDetail, TaskDetailResponse } from "./types";

/** Title, status, 角色 · Agent · 仓库/分支, and the task's actions. */
export function TaskHeader({ task, roleName, connected, client, host, onApplied }: {
  task: TaskDetail;
  roleName: string;
  connected: boolean;
  client: PluginRpcClient;
  host: PluginHostServices;
  onApplied: (response: TaskDetailResponse) => void;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="grid min-w-0 flex-1 gap-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="min-w-0 break-words font-display text-title text-ink">{taskTitle(task)}</h1>
          <StatusLabel status={task.status} className="text-body-sm text-ink-secondary" />
        </div>
        <p className="min-w-0 truncate text-body-sm text-ink-muted" title={`${task.repository} · ${task.branch}`}>
          {roleName} · {agentLabel(task.agent)} · {repositoryName(task.repository)}/{task.branch}
        </p>
      </div>
      <div className="flex shrink-0 gap-2">
        {/* A completed task shows its PR in the delivery summary instead. */}
        {task.pr_url && task.status !== "completed" ? <OpenPullRequestButton url={task.pr_url} host={host} /> : null}
        <CancelTaskButton task={task} connected={connected} client={client} host={host} onApplied={onApplied} />
      </div>
    </div>
  );
}
