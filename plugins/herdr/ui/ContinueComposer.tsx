import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { directPromptAction, type DirectControl } from "./AgentComposer";
import { Composer } from "./Composer";
import { InterruptButton } from "./InterruptButton";
import type { TaskDetail, TaskDetailResponse } from "./types";

/**
 * The always-present 追加要求 input: sending starts the next run of the same
 * agent in the same worktree. Disabled while the service says the task cannot
 * continue or the bridge is down; the parent keys it by task, so a draft
 * never carries over to another task. Once no run owns the agent, `direct`
 * adds 直接发送 (the draft goes to the agent as is, outside the task) and
 * Ctrl+C; while a run is in progress it is absent and the task's 取消 is the
 * way to stop it.
 */
export function ContinueComposer({ task, connected, client, host, onApplied, direct }: {
  task: TaskDetail;
  connected: boolean;
  client: PluginRpcClient;
  host: PluginHostServices;
  onApplied: (response: TaskDetailResponse) => void;
  direct?: DirectControl;
}) {
  const continueTask = {
    label: "发送追加要求",
    errorTitle: "追加要求未提交",
    disabled: !connected || !task.can_continue,
    run: async (requirement: string) => {
      onApplied(await client.call<TaskDetailResponse>("tasks.continue", { task_id: task.id, requirement }));
    },
  };
  return (
    <Composer
      label="追加要求"
      primary={continueTask}
      secondary={direct ? [directPromptAction(client, direct, "直接发送")] : []}
      trailing={direct ? <InterruptButton paneId={direct.paneId} disabled={!direct.enabled} client={client} host={host} onSent={direct.onSent} /> : null}
      host={host}
    />
  );
}
