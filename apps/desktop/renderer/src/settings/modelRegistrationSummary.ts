import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { findProviderPreset } from "./modelProviderPresets";

/** Up to two initials for a registration's list avatar. */
export function registrationInitials(registration: ModelRegistrationFormData): string {
  const source = registration.model || registration.provider || "M";
  const initials = source
    .split(/[\s._/:-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return initials || "M";
}

/** The provider as a person would name it: a preset's label, else the raw provider id. */
export function registrationProviderLabel(registration: ModelRegistrationFormData): string {
  return findProviderPreset(registration)?.label ?? registration.provider.trim();
}

/** The base URL's host (`api.openai.com`), or the raw text when it is not a URL. */
export function registrationHost(registration: ModelRegistrationFormData): string {
  const baseUrl = registration.baseUrl.trim();
  try {
    return new URL(baseUrl).host || baseUrl;
  } catch {
    return baseUrl;
  }
}
