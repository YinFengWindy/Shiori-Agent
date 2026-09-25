import type { BridgeResponse } from "../../../src/bridge/shared";
import type { FeedbackAction } from "../shared/feedback/feedbackStore";
import type { FeedbackPersona } from "../shared/mascot/mascotLines";

/** The bridge error shape a failed `chat.send` reports (or a thrown transport error). */
export type ChatSendFailure = Pick<NonNullable<BridgeResponse["error"]>, "message"> & Partial<NonNullable<BridgeResponse["error"]>>;

/** Where the user can repair a model configuration that blocked sending. */
export type ModelConfigurationRemedy = "choose-role-model" | "open-model-settings";

/**
 * Maps the backend's `model_configuration_required` error (see
 * `core/roles/model_errors.py`) to the place that fixes it: a role without a
 * usable binding is fixed from the composer's model menu, while a missing or
 * incomplete registration can only be fixed in model settings. Any other
 * failure has no dedicated remedy.
 */
export function modelConfigurationRemedy(failure: ChatSendFailure): ModelConfigurationRemedy | null {
  if (failure.code !== "model_configuration_required") return null;
  const reason = String(failure.details?.reason ?? "");
  if (reason === "role_unbound" || reason === "registration_missing") return "choose-role-model";
  return "open-model-settings";
}

/** Builds the error-toast action for a failed send, if the failure has a remedy. */
export function chatSendFailureAction(
  failure: ChatSendFailure,
  remedies: { chooseRoleModel: () => void; openModelSettings: () => void },
): FeedbackAction | undefined {
  const remedy = modelConfigurationRemedy(failure);
  if (remedy === "choose-role-model") return { label: "选择模型", onSelect: remedies.chooseRoleModel };
  if (remedy === "open-model-settings") return { label: "模型设置", onSelect: remedies.openModelSettings };
  return undefined;
}

/**
 * Who fronts a failed send's toast: a model configuration problem gets
 * 吟风's 「还没给我接模型呢」 line, anything else her generic one.
 */
export function chatSendFailurePersona(failure: ChatSendFailure): FeedbackPersona {
  return modelConfigurationRemedy(failure) ? "modelMissing" : "generic";
}
