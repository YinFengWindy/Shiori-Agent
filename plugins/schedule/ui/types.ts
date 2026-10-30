/** How a job runs: send its text as is, or run it as a role turn and send the reply. */
export type ScheduleTier = "instant" | "soft";

/** When a job fires: at a time, after a delay, or on a recurring rule. */
export type ScheduleTrigger = "at" | "after" | "every";

/** The fields the task form edits; the plugin's `create` / `update` RPC take them. */
export type ScheduleTaskFormData = {
  name: string;
  tier: ScheduleTier;
  trigger: ScheduleTrigger;
  when: string;
  content: string;
};

/** One of the role's jobs as the plugin's `list` RPC returns it. */
export type ScheduledTask = {
  id: string;
  role_id: string;
  status: "running" | "scheduled";
  label: string;
  detail: string;
  created_at: string;
  next_run_at: string;
  editable: boolean;
  schedule: Omit<ScheduleTaskFormData, "name">;
};
