import { advanceTypewriter, startTypewriter, type TypewriterProgress, type TypewriterTiming } from "../shared/adv/typewriter";
import type { MascotLine, OnboardingScene } from "./onboardingScript";

/**
 * Pure state of the guide's dialogue box. Unlike the site's scripted ADV,
 * lines arrive as events: a scene opening says its intro, a form action
 * replaces whatever is showing with 吟风's reaction. The box then waits on
 * the last line (the form is up) instead of ending.
 */
export interface OnboardingDialogueState {
  /** The scene these lines belong to; "leaving" while 吟风 answers a skip. */
  readonly scene: OnboardingScene | "leaving" | "";
  readonly lines: readonly MascotLine[];
  readonly index: number;
  readonly progress: TypewriterProgress;
  /** Increases whenever a new line starts; keys one-shot reactions. */
  readonly serial: number;
}

/** Actions the dialogue understands. */
export type OnboardingDialogueAction =
  | { readonly type: "say"; readonly scene: OnboardingDialogueState["scene"]; readonly lines: readonly MascotLine[] }
  | { readonly type: "click" }
  | { readonly type: "tick"; readonly elapsedMs: number };

/** Nothing said yet (the guide is still connecting). */
export const emptyOnboardingDialogue: OnboardingDialogueState = {
  scene: "",
  lines: [],
  index: 0,
  progress: { shownChars: 0, pendingMs: 0 },
  serial: 0,
};

/** The line in the box, or null before anything was said. */
export function currentDialogueLine(state: OnboardingDialogueState): MascotLine | null {
  return state.lines[state.index] ?? null;
}

/** Whether the current line is fully typed out. */
export function isDialogueLineComplete(state: OnboardingDialogueState) {
  const line = currentDialogueLine(state);
  return line !== null && state.progress.shownChars >= line.text.length;
}

/** Whether the box shows the last line of what was said (a form may now appear). */
export function isLastDialogueLine(state: OnboardingDialogueState) {
  return state.lines.length > 0 && state.index === state.lines.length - 1;
}

/** Whether a click still does something: finish typing, or move to the next line. */
export function canAdvanceDialogue(state: OnboardingDialogueState) {
  return currentDialogueLine(state) !== null && (!isDialogueLineComplete(state) || !isLastDialogueLine(state));
}

function startLine(state: OnboardingDialogueState, index: number, timing: TypewriterTiming): OnboardingDialogueState {
  return { ...state, index, progress: startTypewriter(state.lines[index].text.length, timing), serial: state.serial + 1 };
}

/** Applies one action; unchanged state is returned as-is so React skips renders. */
export function onboardingDialogueReducer(state: OnboardingDialogueState, action: OnboardingDialogueAction, timing: TypewriterTiming): OnboardingDialogueState {
  if (action.type === "say") {
    if (!action.lines.length) return { ...emptyOnboardingDialogue, scene: action.scene, serial: state.serial };
    return startLine({ ...state, scene: action.scene, lines: action.lines }, 0, timing);
  }
  const line = currentDialogueLine(state);
  if (!line) return state;
  if (action.type === "tick") {
    const progress = advanceTypewriter(state.progress, action.elapsedMs, line.text.length, timing);
    return progress === state.progress ? state : { ...state, progress };
  }
  // First click completes a typing line; the next moves on; the last line waits.
  if (!isDialogueLineComplete(state)) return { ...state, progress: { shownChars: line.text.length, pendingMs: 0 } };
  return isLastDialogueLine(state) ? state : startLine(state, state.index + 1, timing);
}
