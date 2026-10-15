import { groupTasks, type StatusTone } from "./taskSelectors";
import type { AgentListResponse, AgentSummary, TaskSummary } from "./types";

/** What the page shows: an agent of the session, or a plugin task without one. */
export type Selection = { kind: "agent"; paneId: string } | { kind: "task"; taskId: string };

/** Chinese labels of Herdr's agent states. */
const agentStatusLabels: Record<string, string> = {
  working: "工作中",
  idle: "空闲",
  blocked: "等待输入",
  done: "本轮结束",
  unknown: "状态未知",
};

const agentStatusTones: Record<string, StatusTone> = {
  working: "accent",
  idle: "muted",
  blocked: "warning",
  done: "success",
};

/** Label of a Herdr agent state; an unrecognized state is shown as Herdr names it. */
export function agentStatusLabel(status: string) {
  return agentStatusLabels[status] ?? status;
}

/** Tone of a Herdr agent state. */
export function agentStatusTone(status: string): StatusTone {
  return agentStatusTones[status] ?? "muted";
}

/** Display name of an agent kind; other kinds keep Herdr's name. */
export function agentKindLabel(kind: string) {
  if (kind === "codex") return "Codex";
  if (kind === "claude") return "Claude Code";
  return kind || "Agent";
}

/** The agent's terminal title, else its kind. */
export function agentTitle(agent: Pick<AgentSummary, "title" | "agent">) {
  return agent.title || agentKindLabel(agent.agent);
}

/** Every listed agent, in sidebar order. */
export function listedAgents(agents: AgentListResponse | null) {
  return agents?.workspaces.flatMap((workspace) => workspace.agents) ?? [];
}

/**
 * Plugin tasks no listed agent carries: tasks still starting, tasks whose
 * agent has left the session, and tasks of another session. Without an agent
 * list (session unavailable) that is every task, so delivery stays visible.
 * Unfinished tasks come first, each part newest first.
 */
export function unlinkedTasks(tasks: readonly TaskSummary[], agents: AgentListResponse | null) {
  const linked = new Set(listedAgents(agents).map((agent) => agent.task_id));
  const { active, finished } = groupTasks(tasks.filter((task) => !linked.has(task.id)));
  return [...active, ...finished];
}

/** The selection as the page shows it; a task now carried by a listed agent shows as that agent. */
export type ResolvedSelection =
  | { kind: "agent"; paneId: string; agent: AgentSummary | undefined }
  | { kind: "task"; taskId: string; task: TaskSummary | undefined };

/** Resolves the selection against the current lists; a missing agent or task stays selected. */
export function resolveSelection(selection: Selection | null, agents: AgentListResponse | null, tasks: readonly TaskSummary[]): ResolvedSelection | null {
  if (!selection) return null;
  const all = listedAgents(agents);
  if (selection.kind === "agent") {
    return { kind: "agent", paneId: selection.paneId, agent: all.find((agent) => agent.pane_id === selection.paneId) };
  }
  const carrier = all.find((agent) => agent.task_id === selection.taskId);
  if (carrier) return { kind: "agent", paneId: carrier.pane_id, agent: carrier };
  return { kind: "task", taskId: selection.taskId, task: tasks.find((task) => task.id === selection.taskId) };
}

/** The first entry of the sidebar, picked once nothing is selected yet. */
export function firstSelection(agents: AgentListResponse | null, tasks: readonly TaskSummary[]): Selection | null {
  const agent = listedAgents(agents)[0];
  if (agent) return { kind: "agent", paneId: agent.pane_id };
  const task = unlinkedTasks(tasks, agents)[0];
  return task ? { kind: "task", taskId: task.id } : null;
}
