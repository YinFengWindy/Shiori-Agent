import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { applyProviderPreset } from "./modelProviderPresets";

/** Creates an unsaved model registration, starting from the OpenAI preset. */
export function createModelRegistration(): ModelRegistrationFormData {
  return applyProviderPreset({ id: crypto.randomUUID(), provider: "", baseUrl: "", apiKey: "", model: "", effort: "none", contextWindowTokens: null, maxOutputTokens: null }, "openai");
}

/**
 * Whether a new registration is complete enough to join the saved catalog:
 * the backend reaches every model through provider + base URL + model id.
 * The API key stays optional (local servers such as Ollama need none).
 */
export function isModelRegistrationComplete(registration: ModelRegistrationFormData): boolean {
  return hasModelCapacity(registration) && [registration.provider, registration.baseUrl, registration.model].every((value) => value.trim() !== "");
}

/** Whether explicit model capacities are valid, without guessing from its name. */
export function hasModelCapacity(registration: ModelRegistrationFormData) {
  const { contextWindowTokens, maxOutputTokens } = registration;
  return contextWindowTokens != null && maxOutputTokens != null
    && Number.isSafeInteger(contextWindowTokens) && Number.isSafeInteger(maxOutputTokens)
    && contextWindowTokens > 0 && maxOutputTokens > 0 && maxOutputTokens <= contextWindowTokens;
}
