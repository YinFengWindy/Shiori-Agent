import { useEffect, useRef, useState } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import { onboardingReactionLine, onboardingSceneLines, type OnboardingReaction, type OnboardingScene } from "./onboardingScript";
import { useOnboardingDialogue } from "./useOnboardingDialogue";

/** How long 吟风's answer to 「跳过」 stays up before the guide closes. */
const LEAVE_DWELL_MS = 1200;

/**
 * Directs the guide's ADV: says each scene's opening lines when the scene
 * changes, raises the form once those lines reach their last one, answers
 * form actions, and plays the skip line before dismissing.
 */
export function useOnboardingScene({ scene, roleName, paused, onSkip }: { scene: OnboardingScene; roleName: string; paused: boolean; onSkip: () => void }) {
  const dialogue = useOnboardingDialogue(paused);
  const { say } = dialogue;
  const [revealedScene, setRevealedScene] = useState<OnboardingScene | null>(null);
  const [leaving, setLeaving] = useState(false);
  // Last scene whose lines were said; the greeting plays only before the first.
  const saidScene = useRef<OnboardingScene | null>(null);

  useEffect(() => {
    if (scene === "loading" || leaving || saidScene.current === scene) return;
    const greet = saidScene.current === null;
    saidScene.current = scene;
    say(scene, onboardingSceneLines(scene, { greet, roleName }));
  }, [scene, roleName, leaving, say]);

  // The form rises with the scene's last line and stays up through reactions.
  const introDone = dialogue.scene === scene && dialogue.lastLine;
  useEffect(() => {
    if (introDone && revealedScene !== scene) setRevealedScene(scene);
  }, [introDone, revealedScene, scene]);

  const leaveReady = leaving && dialogue.scene === "leaving" && dialogue.complete;
  // The controller's skip changes identity every render; the timer must not restart.
  const onSkipRef = useLatestRef(onSkip);
  useEffect(() => {
    if (!leaveReady) return;
    const timer = window.setTimeout(() => onSkipRef.current(), LEAVE_DWELL_MS);
    return () => window.clearTimeout(timer);
  }, [leaveReady, onSkipRef]);

  return {
    dialogue,
    formVisible: !leaving && revealedScene === scene,
    leaving,
    /** 吟风 answers one form action in the current scene. */
    react: (reaction: OnboardingReaction) => say(scene, [onboardingReactionLine(reaction)]),
    /** Plays the skip line, then dismisses (sooner if the user clicks on). */
    skip: () => {
      setLeaving(true);
      say("leaving", [onboardingReactionLine(scene === "role" ? "skipRole" : "skipModel")]);
    },
    /** Click / Enter / Space on the stage. */
    advance: () => {
      if (leaveReady) onSkip();
      else dialogue.click();
    },
  };
}
