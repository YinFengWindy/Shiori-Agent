/*
 * The one-time English prompt on the Chinese pages (#806): a visitor whose
 * browser asks for no Chinese at all is offered the English site once, in
 * English (the English dictionary's `languagePrompt`: 「View this site in
 * English?」, Switch or Dismiss) — and either
 * answer is remembered, so it never asks again. Nothing switches by itself.
 * Pure, so the decision is unit-testable; LanguagePrompt.astro drives it.
 */

/** localStorage key of the visitor's answer. */
export const LANGUAGE_PROMPT_STORAGE_KEY = "shiori-site-language-prompt";

/** What the visitor answered: the stored value. */
export type LanguagePromptAnswer = "switched" | "dismissed";

/**
 * What the visitor's storage says about the prompt: nothing yet
 * (`unanswered`), an answer (`answered`), or nothing can be read
 * (`unreadable`: storage blocked), in which case the prompt stays away
 * rather than ask on every page.
 */
export type LanguagePromptMemory = "unanswered" | "answered" | "unreadable";

/** The memory a stored value (`localStorage.getItem`) stands for: any value is an answer. */
export function languagePromptMemory(stored: string | null): LanguagePromptMemory {
  return stored === null ? "unanswered" : "answered";
}

/**
 * Whether to offer the English site: only while the visitor has not
 * answered (`memory`), and only when the browser names its languages
 * (`navigator.languages`) and none of them is Chinese (`zh`, `zh-CN`,
 * `zh-Hant-TW`, …).
 */
export function shouldOfferEnglish(languages: readonly string[], memory: LanguagePromptMemory): boolean {
  if (memory !== "unanswered") return false;
  if (languages.length === 0) return false;
  return !languages.some((language) => /^zh(?:-|$)/i.test(language.trim()));
}
