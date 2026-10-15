/** Public JSON contract of the Herdr plugin: dashboard RPC (`tasks.*`), `sessions.list` and its config. */

/** Lifecycle owned by the task service. */
export type TaskStatus =
  | "queued"
  | "preparing"
  | "running"
  | "completed"
  | "blocked"
  | "unknown"
  | "failed"
  | "cancelling"
  | "cancelled"
  | "monitoring_stopped";

/** Reported stages; a run may legitimately move back to an earlier one. */
export type TaskStage = "preparing" | "analysis" | "implementation" | "validation" | "pull_request";

/** One task list entry. */
export type TaskSummary = {
  id: string;
  title: string;
  status: TaskStatus;
  /** Nothing more is asked of the user (the service decides; blocked and unknown are not finished). */
  finished: boolean;
  stage: TaskStage | "";
  progress_detail: string;
  progress_updated_at: string;
  role_id: string;
  agent: "codex" | "claude";
  repository: string;
  branch: string;
  created_at: string;
  updated_at: string;
  revision: number;
};

/** One accepted stage report of the current run. */
export type ProgressEvent = { run_id: string; sequence: number; stage: TaskStage; detail: string; source: string; observed_at: string };

/** A validation command the plugin actually ran, including failures. */
export type TaskValidation = { argv: string[]; cwd: string; exit_code: number | null; output: string };

/** The selected task's full state; action availability is decided by the service. */
export type TaskDetail = TaskSummary & {
  run_id: string;
  requirement: string;
  worktree: string;
  output: string;
  progress_events: ProgressEvent[];
  progress_notice: string;
  validation: TaskValidation[];
  summary: string;
  pr_url: string;
  error: string;
  report_error: string;
  can_continue: boolean;
  can_cancel: boolean;
};

/** `tasks.list`, newest first; `instance_id` tells a fresh plugin process from retained revisions. */
export type TaskListResponse = { instance_id: string; tasks: TaskSummary[] };

/** `tasks.get`, `tasks.continue` and `tasks.cancel`. */
export type TaskDetailResponse = { instance_id: string; task: TaskDetail };

/** `tasks.changed` payload: an invalidation, never task state. */
export type TaskChange = { task_id: string; revision: number };

/** The plugin config (`HerdrConfig`) as the settings page edits it through `host.config`. */
export type HerdrSettings = {
  executable: string;
  session: string;
  default_agent: "codex" | "claude";
  codex_model: string;
  claude_model: string;
  cli_timeout_seconds: number;
  task_timeout_seconds: number;
};

/** One local Herdr session as `sessions.list` reports it. */
export type HerdrSession = { name: string; status: "running" | "stopped" };

/** `sessions.list`: every session Herdr knows on this machine. */
export type SessionListResponse = { sessions: HerdrSession[] };
