import type { DesktopApi } from "../../../src/bridge/shared";
import { BridgeError, type RoleRecord } from "@shiori/sdk";
import type { NewRoleFormState } from "../shared/types";

/** Builds the shared manual/import request and validates required role fields. */
export function buildRoleCreationRequest(form: NewRoleFormState) {
  const name = form.name.trim();
  const character = form.profile?.character;
  const systemPrompt = character
    ? [character.behavior_rules, character.profile, character.personality, character.response_constraints].find((text) => text?.trim())?.trim() ?? ""
    : form.systemPrompt.trim();
  if (!name || (!form.importId && !systemPrompt)) throw new Error("角色名称和系统提示词不能为空。");
  const fields = {
    name,
    description: form.description,
    ...(!form.importId || !form.profile ? { system_prompt: systemPrompt } : {}),
    ...(form.profile ? { profile: form.profile } : {}),
    ...(form.avatarSource !== undefined ? { avatar_source: form.avatarSource } : {}),
  };
  return form.importId
    ? { method: "roles.cardImport.commit", payload: { import_id: form.importId, overrides: fields, emotion_selections: form.emotionSelections ?? {} } }
    : { method: "roles.create", payload: fields };
}

/** Persists a role without coupling creation to a particular screen's navigation. */
export async function createRoleFromDraft(form: NewRoleFormState, invoke: DesktopApi["invoke"]) {
  const response = await invoke(buildRoleCreationRequest(form));
  if (response.error) throw new BridgeError(response.error.message, response.error.code, response.error.details);
  const role = response.payload.role as RoleRecord | undefined;
  if (!role?.id) throw new Error("创建结果缺少角色信息");
  return role;
}
