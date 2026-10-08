import type { AffectionStagePrompt, AffectionStagePromptChanges } from "./affectionStagePrompts";

/** Field text per stage name. */
export type StagePromptTexts = Record<string, string>;

/** One rendered stage field. */
export type StagePromptRow = {
  stage: string;
  text: string;
  /** Whether 「恢复默认」 applies: the field's text differs from the default. */
  overridden: boolean;
};

/**
 * Whether `text` overrides `defaultText`; mirrors the backend rule, so a blank
 * field or the default's own text counts as the default.
 */
export function isStagePromptOverride(text: string, defaultText: string) {
  const trimmed = text.trim();
  return trimmed !== "" && trimmed !== defaultText;
}

/** The field texts a loaded answer starts from: each stage's injected guidance. */
export function stagePromptTexts(stages: readonly AffectionStagePrompt[]): StagePromptTexts {
  return Object.fromEntries(stages.map((item) => [item.stage, item.prompt]));
}

/**
 * The write request the field texts amount to: every stage in stage order,
 * the trimmed override or `null` where the default applies. Two texts that
 * store the same overrides give equal requests, so it doubles as the saved form.
 */
export function stagePromptRequest(stages: readonly AffectionStagePrompt[], texts: StagePromptTexts): AffectionStagePromptChanges {
  return Object.fromEntries(stages.map((item) => {
    const text = texts[item.stage] ?? item.prompt;
    return [item.stage, isStagePromptOverride(text, item.default) ? text.trim() : null];
  }));
}

/**
 * Only the stages of `request` that differ from `baseline`, this editor's own
 * last known form (what it loaded, then what it last submitted): what one save
 * writes. Diffing against its own baseline, not the server's answer, keeps
 * stages changed elsewhere out of the write unless this editor touched them.
 */
export function changedStagePrompts(request: AffectionStagePromptChanges, baseline: AffectionStagePromptChanges): AffectionStagePromptChanges {
  return Object.fromEntries(Object.entries(request).filter(([stage, text]) => text !== (baseline[stage] ?? null)));
}

/** The fields to render, in stage order. */
export function stagePromptRows(stages: readonly AffectionStagePrompt[], texts: StagePromptTexts): StagePromptRow[] {
  return stages.map((item) => {
    const text = texts[item.stage] ?? item.prompt;
    return { stage: item.stage, text, overridden: isStagePromptOverride(text, item.default) };
  });
}
