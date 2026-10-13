/*
 * The one-time English prompt on the Chinese pages (#806): a visitor whose
 * browser asks for no Chinese at all is offered the English site once, in
 * English — 「View this site in English?」, Switch or Dismiss — and either
 * answer is remembered, so it never asks again. Nothing switches by itself.
 * Pure, so the decision is unit-testable; LanguagePrompt.astro drives it.
 */

/** localStorage key of the visitor's answer. */
export const LANGUAGE_PROMPT_STORAGE_KEY = "shiori-site-language-prompt";

/** What the visitor answered: the stored value. */
export type LanguagePromptAnswer = "switched" | "dismissed";

/**
 * The prompt's words: English whatever the page's language, as it speaks to
 * a visitor who reads no Chinese.
 */
export const LANGUAGE_PROMPT_TEXT = {
  question: "View this site in English?",
  switch: "Switch",
  dismiss: "Dismiss",
  label: "Language",
} as const;

/**
 * Whether to offer the English site: not once the visitor has answered
 * (`stored`, anything stored counts), and only when the browser names its
 * languages (`navigator.languages`) and none of them is Chinese (`zh`,
 * `zh-CN`, `zh-Hant-TW`, …).
 */
export function shouldOfferEnglish(languages: readonly string[], stored: string | null): boolean {
  if (stored !== null) return false;
  if (languages.length === 0) return false;
  return !languages.some((language) => /^zh(?:-|$)/i.test(language.trim()));
}
