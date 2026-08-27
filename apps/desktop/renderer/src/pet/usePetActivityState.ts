import { useEffect, useRef, useState } from "react";
import { transitionPetActivity, type PetActivityTransition } from "./activity";
import type { SpriteState } from "./spriteContract";

/** Lets a proactive message complete its Codex waving acknowledgement before waiting. */
export const petNotificationAnimationMs = 720;

/** Subscribes to bridge activity while keeping brief notification animation above task status. */
export function usePetActivityState(initialState: SpriteState): SpriteState {
  const [state, setState] = useState<SpriteState>(initialState);
  const activitiesRef = useRef<PetActivityTransition["activities"]>({});
  const notificationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    activitiesRef.current = {};
    setState(initialState);
  }, [initialState]);

  useEffect(() => {
    const clearNotificationTimer = () => {
      if (notificationTimerRef.current) clearTimeout(notificationTimerRef.current);
      notificationTimerRef.current = null;
    };
    const off = window.miraDesktop.onEvent((event) => {
      const transition = transitionPetActivity(activitiesRef.current, event);
      if (!transition.handled) return;
      activitiesRef.current = transition.activities;
      clearNotificationTimer();
      if (!transition.showNotification) {
        setState(transition.state);
        return;
      }
      setState("waving");
      notificationTimerRef.current = setTimeout(() => {
        notificationTimerRef.current = null;
        setState(transition.state);
      }, petNotificationAnimationMs);
    });
    return () => {
      clearNotificationTimer();
      off();
    };
  }, []);

  return state;
}
