import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import type { RoleRecord } from "../shared/types";
import { normalizeModelEffort } from "./modelEffort";

/** Supported reasoning effort values exposed by model controls. */
export type ModelEffort = ModelRegistrationFormData["effort"];

/** Effective role-owned model and effort selections shown in the chat menu. */
export type RoleModelSelection = {
  dialogueId: string;
  visualId: string;
  dialogueEffort: ModelEffort;
  visualEffort: ModelEffort;
  runtimeConfig: Record<string, unknown>;
};

/** Resolves role model controls, falling back to the selected registration defaults. */
export function selectionFromRole(
  role: RoleRecord,
  registrations: ModelRegistrationFormData[],
): RoleModelSelection {
  const dialogueId = String(role.runtime_config.dialogue_model_registration_id ?? "");
  const dialogue = registrations.find((registration) => registration.id === dialogueId);
  const fallbackEffort = dialogue?.effort ?? "none";
  const visualId = String(role.runtime_config.visual_model_registration_id ?? "");
  const visual = registrations.find((registration) => registration.id === visualId) ?? dialogue;
  const effortFromRole = (key: string, fallback: ModelEffort) => {
    return normalizeModelEffort(role.runtime_config[key], fallback);
  };
  return {
    dialogueId,
    visualId,
    dialogueEffort: effortFromRole("dialogue_model_effort", fallbackEffort),
    visualEffort: effortFromRole("visual_model_effort", visual?.effort ?? "none"),
    runtimeConfig: role.runtime_config,
  };
}

/** Builds the role runtime config for one chat model control change. */
export function runtimeConfigForSelection(
  selection: RoleModelSelection,
  kind: "dialogue" | "visual" | "dialogueEffort" | "visualEffort",
  value: string,
): Record<string, unknown> {
  return {
    ...selection.runtimeConfig,
    dialogue_model_registration_id: kind === "dialogue" ? value : selection.dialogueId,
    visual_model_registration_id: kind === "visual" ? value : selection.visualId,
    dialogue_model_effort: kind === "dialogueEffort" ? value : selection.dialogueEffort,
    visual_model_effort: kind === "visualEffort" ? value : selection.visualEffort,
  };
}
