import { useEffect, useRef, useState } from "react";
import { transitionPetActivity, type PetActivityTransition } from "./activity";
import type { SurfaceHandle } from "@yinfengwindy/shiori-sdk";
import type { SpriteState } from "./spriteContract";

/** Lets a proactive message complete its Codex waving acknowledgement before waiting. */
export const petNotificationAnimationMs = 720;

/** Retains plugin animation priority while consuming only typed role activity. */
export function usePetActivityState(surface: SurfaceHandle, initialState: SpriteState): SpriteState {
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
    const off = surface.onRoleActivity((event) => {
      if (!event) {
        activitiesRef.current = {};
        clearNotificationTimer();
        setState("idle");
        return;
      }
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
  }, [surface]);

  return state;
}
