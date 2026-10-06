
/** The role a surface can interact with; visibility and window lifetime remain host-owned. */
export type SurfaceInteractionTarget = { roleId: string; available: boolean };

/** Role-scoped activity. The plugin decides which animation represents each phase. */
export type SurfaceRoleActivity = {
  roleId: string;
  sessionKey: string;
  phase: "running" | "review" | "failed" | "waiting";
  notify: boolean;
};
