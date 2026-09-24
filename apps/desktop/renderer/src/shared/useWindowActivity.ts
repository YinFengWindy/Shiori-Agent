import { useEffect, useState } from "react";

/** Whether the window is shown and whether it has focus. */
export type WindowActivity = { visible: boolean; focused: boolean };

function readWindowActivity(): WindowActivity {
  if (typeof document === "undefined") return { visible: true, focused: true };
  return { visible: !document.hidden, focused: document.hasFocus() };
}

/**
 * Tracks page visibility and window focus, so heavy or ambient visuals can
 * pause while nobody is looking (hidden) or the user is in another app
 * (blurred).
 */
export function useWindowActivity(): WindowActivity {
  const [activity, setActivity] = useState(readWindowActivity);

  useEffect(() => {
    const update = () => {
      setActivity((current) => {
        const next = readWindowActivity();
        return current.visible === next.visible && current.focused === next.focused ? current : next;
      });
    };
    update();
    document.addEventListener("visibilitychange", update);
    window.addEventListener("focus", update);
    window.addEventListener("blur", update);
    return () => {
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("focus", update);
      window.removeEventListener("blur", update);
    };
  }, []);

  return activity;
}
