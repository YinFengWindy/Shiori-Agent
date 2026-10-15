import { useEffect, useMemo, useSyncExternalStore } from "react";
import type { PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { TaskFeed, type FeedSource } from "./taskFeed";
import type { TaskDetailResponse } from "./types";

/** Only a newer revision from the same plugin process replaces the shown detail. */
export function mergeTaskDetail(current: TaskDetailResponse | null, next: TaskDetailResponse) {
  if (!current || current.instance_id !== next.instance_id || next.task.revision > current.task.revision) return next;
  return current;
}

function detailSource(taskId: string): FeedSource<TaskDetailResponse> {
  return {
    read: (client) => client.call<TaskDetailResponse>("tasks.get", { task_id: taskId }),
    merge: mergeTaskDetail,
    invalidatedBy: (current, change) => change.task_id === taskId && (!current || change.revision > current.task.revision),
  };
}

/** Follows one task's full state while its detail view is mounted. */
export function useTaskDetail(client: PluginRpcClient, host: PluginHostServices, taskId: string) {
  const feed = useMemo(() => new TaskFeed(detailSource(taskId)), [taskId]);
  useEffect(() => {
    void feed.start(client, host);
    return () => feed.stop();
  }, [feed, client, host]);
  return { state: useSyncExternalStore(feed.subscribe, feed.getSnapshot, feed.getSnapshot), feed };
}
