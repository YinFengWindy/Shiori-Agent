import type { PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/** One stage's guidance as the affection plugin reports it. */
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
export async function readAffectionStagePrompts(client: PluginRpcClient, roleId: string) {
  return checkedRole(await client.call<AffectionStagePrompts>("stage_prompts_get", { role_id: roleId }), roleId);
}

/** Writes the named stages and answers with every stage as stored. */
export async function writeAffectionStagePrompts(client: PluginRpcClient, roleId: string, prompts: AffectionStagePromptChanges) {
  return checkedRole(await client.call<AffectionStagePrompts>("stage_prompts_set", { role_id: roleId, prompts }), roleId);
}
