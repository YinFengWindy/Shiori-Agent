import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** One stage's guidance as `roles.affection.stagePrompts.*` reports it. */
export type AffectionStagePrompt = {
  stage: string;
  /** The guidance injected for this stage: the role's override, else the default. */
  prompt: string;
  default: string;
  overridden: boolean;
};

/** Every stage's guidance of one role, in stage order. */
export type AffectionStagePrompts = {
  role_id: string;
  stages: AffectionStagePrompt[];
};

/** Per-stage text to write; `null`, blank or the default text restores the default. */
export type AffectionStagePromptChanges = Record<string, string | null>;

function checkedRole(response: AffectionStagePrompts, roleId: string) {
  if (response.role_id !== roleId) throw new Error("角色不匹配");
  return response;
}

/** Reads the role's stage guidance. */
export async function readAffectionStagePrompts(invoke: DesktopInvoke, roleId: string) {
  return checkedRole(await invokeBridgePayload<AffectionStagePrompts>(invoke, "roles.affection.stagePrompts.get", { role_id: roleId }), roleId);
}

/** Writes the named stages and answers with every stage as stored. */
export async function writeAffectionStagePrompts(invoke: DesktopInvoke, roleId: string, prompts: AffectionStagePromptChanges) {
  return checkedRole(await invokeBridgePayload<AffectionStagePrompts>(invoke, "roles.affection.stagePrompts.set", { role_id: roleId, prompts }), roleId);
}
