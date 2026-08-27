/** Stable five-stage expression order shared by the progress UI and bridge job. */
export const roleDifferenceStages = [
  { id: "neutral", label: "平静" },
  { id: "happy", label: "开心" },
  { id: "surprised", label: "惊讶" },
  { id: "angry", label: "生气" },
  { id: "sad", label: "悲伤" },
] as const;

/** Supported generated-expression identifiers. */
export type RoleDifferenceStageId = (typeof roleDifferenceStages)[number]["id"];
/** Per-stage status shown while one difference job is running. */
export type RoleDifferenceStageStatus = "pending" | "generating" | "completed" | "failed";

/** Renderer-facing stage snapshot for a role-difference job. */
export type RoleDifferenceStage = {
  id: RoleDifferenceStageId;
  label: string;
  status: RoleDifferenceStageStatus;
  error: string;
};

/** Renderer-facing state for the role-difference generation panel. */
export type RoleDifferenceGenerationState = {
  status: "idle" | "running" | "success" | "error";
  jobId: string;
  completed: number;
  current: RoleDifferenceStageId | "";
  categoryName: string;
  error: string;
  stages: RoleDifferenceStage[];
};

/** Untrusted bridge progress payload normalized by the renderer state helper. */
export type RoleDifferenceProgressPayload = {
  job_id?: unknown;
  role_id?: unknown;
  phase?: unknown;
  current?: unknown;
  completed?: unknown;
  category_name?: unknown;
  error?: unknown;
  stages?: unknown;
};

/** Creates the idle state for one role's difference-generation panel. */
export function createRoleDifferenceGenerationState(): RoleDifferenceGenerationState {
  return {
    status: "idle",
    jobId: "",
    completed: 0,
    current: "",
    categoryName: "",
    error: "",
    stages: roleDifferenceStages.map((stage) => ({
      ...stage,
      status: "pending",
      error: "",
    })),
  };
}

/** Applies one bridge progress event without trusting arbitrary stage ids. */
export function applyRoleDifferenceProgress(
  current: RoleDifferenceGenerationState,
  payload: RoleDifferenceProgressPayload,
): RoleDifferenceGenerationState {
  const phase = typeof payload.phase === "string" ? payload.phase : "";
  const stages = current.stages.map((stage) => ({ ...stage }));
  if (Array.isArray(payload.stages)) {
    for (const rawStage of payload.stages) {
      if (!rawStage || typeof rawStage !== "object") continue;
      const stagePayload = rawStage as Record<string, unknown>;
      const stage = stages.find((item) => item.id === stagePayload.id);
      if (!stage) continue;
      const status = stagePayload.status;
      if (status === "pending" || status === "generating" || status === "completed" || status === "failed") {
        stage.status = status;
      }
      stage.error = typeof stagePayload.error === "string" ? stagePayload.error : "";
    }
  }
  const completed = typeof payload.completed === "number"
    ? Math.max(0, Math.min(roleDifferenceStages.length, payload.completed))
    : current.completed;
  const currentStage = roleDifferenceStages.some((stage) => stage.id === payload.current)
    ? payload.current as RoleDifferenceStageId
    : "";
  const status = phase === "finished"
    ? "success"
    : phase === "failed"
      ? "error"
      : phase === "started" || phase === "generating" || phase === "completed"
        ? "running"
        : current.status;
  return {
    ...current,
    status,
    jobId: typeof payload.job_id === "string" ? payload.job_id : current.jobId,
    completed,
    current: currentStage,
    categoryName: typeof payload.category_name === "string" ? payload.category_name : current.categoryName,
    error: typeof payload.error === "string" ? payload.error : phase === "finished" ? "" : current.error,
    stages,
  };
}
