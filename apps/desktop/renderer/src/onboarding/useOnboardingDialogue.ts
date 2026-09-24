import { useMemo, useReducer } from "react";
import { useFrameTicker } from "../shared/adv/useFrameTicker";
import { usePrefersReducedMotion } from "../shared/usePrefersReducedMotion";
import {
  canAdvanceDialogue,
  currentDialogueLine,
  emptyOnboardingDialogue,
  isDialogueLineComplete,
  isLastDialogueLine,
  onboardingDialogueReducer,
  type OnboardingDialogueAction,
  type OnboardingDialogueState,
} from "./onboardingDialogue";
import type { MascotLine } from "./onboardingScript";

/** Typewriter speed: the site's 「普通」 text speed. */
const MS_PER_CHAR = 45;

/** React driver for the guide's dialogue: a frame loop types the current line. */
export function useOnboardingDialogue() {
  const reducedMotion = usePrefersReducedMotion();
  const timing = useMemo(() => ({ msPerChar: MS_PER_CHAR, reducedMotion }), [reducedMotion]);
  const [state, dispatch] = useReducer(
    (current: OnboardingDialogueState, action: OnboardingDialogueAction) => onboardingDialogueReducer(current, action, timing),
    emptyOnboardingDialogue,
  );
  const line = currentDialogueLine(state);
  const complete = isDialogueLineComplete(state);
  useFrameTicker(line !== null && !complete, (elapsedMs) => dispatch({ type: "tick", elapsedMs }));
  const actions = useMemo(() => ({
    say: (scene: OnboardingDialogueState["scene"], lines: readonly MascotLine[]) => dispatch({ type: "say", scene, lines }),
    click: () => dispatch({ type: "click" }),
  }), []);
  return {
    scene: state.scene,
    line,
    serial: state.serial,
    shownChars: state.progress.shownChars,
    complete,
    lastLine: isLastDialogueLine(state),
    canAdvance: canAdvanceDialogue(state),
    ...actions,
  };
}
