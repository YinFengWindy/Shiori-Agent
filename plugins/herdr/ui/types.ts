/** Public JSON contract of the Herdr plugin's task snapshot RPC. */
export type TaskStatus = "queued" | "preparing" | "running" | "completed" | "blocked" | "unknown" | "failed" | "cancelling" | "cancelled" | "monitoring_stopped";
/** Actual stages reported by the host or coding agent; ordering may move backwards. */
export type TaskStage = "preparing" | "analysis" | "implementation" | "validation" | "pull_request";
/** One bounded, accepted report from the current run. */
export type ProgressEvent = { run_id: string; sequence: number; stage: TaskStage; detail: string; source: string; observed_at: string };
/** A verified command result, including real failures. */
export type TaskValidation = { argv: string[]; cwd: string; exit_code: number | null; output: string };
/** The task service owns every state and revision exposed here. */
export type HerdrTask = {
  id: string; run_id: string; role_id: string; thread_id: string; agent: "codex" | "claude";
  requirement: string; repository: string; worktree: string; branch: string;
  status: TaskStatus; agent_state: string; summary: string; validation: TaskValidation[];
  pr_url: string; error: string; report_error: string; output: string;
  created_at: string; updated_at: string; revision: number;
  stage: TaskStage | ""; progress_updated_at: string; progress_notice: string;
  progress_events: ProgressEvent[]; can_continue: boolean;
};
/** A process identity disambiguates a fresh application from retained task revisions. */
export type TaskSnapshot = { instance_id: string; tasks: HerdrTask[] };
