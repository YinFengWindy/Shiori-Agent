import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { ContinueComposer } from "./ContinueComposer";
import { DeliverySummary } from "./DeliverySummary";
import { StageTrack } from "./StageTrack";
import { TaskHeader } from "./TaskHeader";
import { TaskSections } from "./TaskSections";
import { TaskTerminal } from "./TaskTerminal";
import { disconnectedMessage } from "./taskFeed";
import { useTaskDetail } from "./useTaskDetail";

/** The selected task: header and stages, terminal, folded records, then the 追加要求 input. */
export function TaskDetailView({ taskId, roleName, listConnected, client, host }: {
  taskId: string;
  roleName: string;
  /** The page already reports a lost connection once; the detail only follows it. */
  listConnected: boolean;
  client: PluginRpcClient;
  host: PluginHostServices;
}) {
  const { state, feed } = useTaskDetail(client, host, taskId);
  const task = state.value?.task;
  const connected = listConnected && state.connected;
  const readError = state.error && state.error !== disconnectedMessage ? state.error : "";
  if (!task) {
    return readError ? <host.ui.InlineError title="任务读取失败" message={readError} layout="card" className="m-6" /> : null;
  }
  return (
    <article className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)_auto]" aria-label="任务详情">
      <header className="grid gap-4 border-b border-line-soft px-6 pb-4 pt-5">
        <TaskHeader task={task} roleName={roleName} connected={connected} client={client} host={host} onApplied={feed.apply} />
        <StageTrack task={task} />
      </header>
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-6 py-4">
        {readError ? <host.ui.InlineError title="任务读取失败" message={readError} layout="row" /> : null}
        {task.error ? <host.ui.InlineError title="任务需要处理" message={task.error} layout="row" /> : null}
        {task.report_error ? <host.ui.InlineError title="聊天回报失败" message={task.report_error} layout="row" /> : null}
        {task.status === "completed" ? <DeliverySummary task={task} host={host} /> : null}
        <TaskTerminal key={task.run_id} output={task.output} />
        <TaskSections task={task} />
      </div>
      <ContinueComposer task={task} connected={connected} client={client} host={host} onApplied={feed.apply} />
    </article>
  );
}
