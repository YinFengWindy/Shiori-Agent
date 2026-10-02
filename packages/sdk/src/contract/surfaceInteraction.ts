import type { VoiceStatePayload } from "./voice";

/** The role a surface can interact with; visibility and window lifetime remain host-owned. */
export type SurfaceInteractionTarget = { roleId: string; available: boolean };

/** Explicit pointer gestures accepted by the host's voice implementation. */
export type SurfaceVoiceGesture = "press" | "move" | "release" | "cancel";

/** Host voice input and state, bound to the receiving surface's window identity. */
export type SurfaceVoice = {
  gesture(gesture: SurfaceVoiceGesture): void;
  onState(listener: (state: VoiceStatePayload) => void): () => void;
};

/** Role-scoped activity. The plugin decides which animation represents each phase. */
export type SurfaceRoleActivity = {
  roleId: string;
  sessionKey: string;
  phase: "running" | "review" | "failed" | "waiting";
  notify: boolean;
};
