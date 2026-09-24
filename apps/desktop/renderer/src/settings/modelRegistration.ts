import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { applyProviderPreset } from "./modelProviderPresets";

/** Creates an unsaved model registration, starting from the OpenAI preset. */
export function createModelRegistration(): ModelRegistrationFormData {
  return applyProviderPreset({ id: crypto.randomUUID(), provider: "", baseUrl: "", apiKey: "", model: "", effort: "none" }, "openai");
}
