import type { ModelRegistrationFormData } from "../../../src/shared";
import type { RoleRecord } from "../shared/types";

export type ModelEffort = ModelRegistrationFormData["effort"];

const MODEL_EFFORTS = new Set<ModelEffort>(["none", "low", "high", "max"]);

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
    const raw = String(role.runtime_config[key] ?? fallback);
    return MODEL_EFFORTS.has(raw as ModelEffort) ? raw as ModelEffort : fallback;
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
