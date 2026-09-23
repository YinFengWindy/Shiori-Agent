import { useEffect, useMemo, useReducer } from "react";
import { useFrameTicker } from "../hooks/useFrameTicker";
import {
  advChoices,
  advReducer,
  choicePrompt,
  createAdvState,
  currentArt,
  currentTopic,
  currentLine,
  isLineComplete,
  type AdvAction,
  type AdvArt,
  type AdvConfig,
  type AdvState,
} from "./advModel";

interface UseAdvDialogueOptions<Art extends AdvArt> extends AdvConfig<Art> {
  /** Freeze typing and auto mode (e.g. while the backlog or settings is open). */
  readonly paused: boolean;
  /** Called once when the closing lines finish. */
  readonly onEnd: () => void;
}

/**
 * React driver for the pure ADV state machine: a requestAnimationFrame loop
 * feeds `tick` while a line is typing or auto mode is waiting, and the
 * derived view (line, art, choices, prompt) is computed from the state.
 */
export function useAdvDialogue<Art extends AdvArt>({ script, msPerChar, reducedMotion, paused, onEnd }: UseAdvDialogueOptions<Art>) {
  const config = useMemo(() => ({ script, msPerChar, reducedMotion }), [script, msPerChar, reducedMotion]);
  // The reducer closes over the latest config, so a text-speed change takes
  // effect on the very next tick.
  const [state, dispatch] = useReducer(
    (current: AdvState, action: AdvAction) => advReducer(current, action, config),
    config,
    (initial: AdvConfig<Art>) => createAdvState(initial),
  );

  const line = currentLine(state, script);
  const complete = isLineComplete(state, script);
  const ticking = !paused && line !== null && (!complete || state.autoMode);
  useFrameTicker(ticking, (elapsedMs) => dispatch({ type: "tick", elapsedMs }));

  useEffect(() => {
    if (state.phase === "ended") onEnd();
  }, [state.phase, onEnd]);

  const actions = useMemo(
    () => ({
      click: () => dispatch({ type: "click" }),
      skip: () => dispatch({ type: "skip" }),
      toggleAuto: () => dispatch({ type: "toggleAuto" }),
      choose: (choiceId: string) => dispatch({ type: "choose", choiceId }),
    }),
    [],
  );

  return {
    phase: state.phase,
    line,
    /** Changes whenever a new line starts (each line is logged exactly once). */
    lineKey: state.backlog.length,
    shownChars: state.shownChars,
    complete,
    autoMode: state.autoMode,
    backlog: state.backlog,
    art: currentArt(state, script),
    topicLabel: currentTopic(state, script)?.label ?? null,
    prompt: choicePrompt(state, script),
    choices: state.phase === "choice" ? advChoices(state, script) : [],
    ...actions,
  };
}
