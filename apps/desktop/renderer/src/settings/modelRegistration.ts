import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelCapacityError } from "../../../src/settingsContract.js";
import { applyProviderPreset } from "./modelProviderPresets";

/** Creates an unsaved model registration, starting from the OpenAI preset. */
export function createModelRegistration(): ModelRegistrationFormData {
  return applyProviderPreset({ id: crypto.randomUUID(), provider: "", baseUrl: "", apiKey: "", model: "", effort: "none", modelContextWindow: null, modelAutoCompactTokenLimit: null }, "openai");
}

/**
 * Whether a new registration is complete enough to join the saved catalog:
 * the backend reaches every model through provider + base URL + model id.
 * The API key stays optional (local servers such as Ollama need none).
 */
export function isModelRegistrationComplete(registration: ModelRegistrationFormData): boolean {
  return hasModelCapacity(registration) && [registration.provider, registration.baseUrl, registration.model].every((value) => value.trim() !== "");
}

/** Whether the explicit window is filled and every entered capacity is valid, without guessing from its name. */
export function hasModelCapacity(registration: ModelRegistrationFormData) {
  return registration.modelContextWindow != null && modelCapacityError(registration) === null;
}
