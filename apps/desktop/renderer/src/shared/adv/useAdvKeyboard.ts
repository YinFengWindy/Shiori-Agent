import { useEffect } from "react";

/** Keys that advance dialogue, galgame style. */
const ADVANCE_KEYS = new Set(["Enter", " "]);

/**
 * Enter / Space advance the dialogue (complete the line, then move on)
 * unless focus is on a control that already handles those keys itself
 * (a button, link or input) or inside an open dialog. Pass a stable
 * `onAdvance` so the listener is not re-attached every render.
 */
export function useAdvKeyboard(enabled: boolean, onAdvance: () => void) {
  useEffect(() => {
    if (!enabled) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (!ADVANCE_KEYS.has(event.key) || event.repeat || event.defaultPrevented) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("button, a, input, textarea, select, [role='dialog']")) return;
      event.preventDefault();
      onAdvance();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, onAdvance]);
}
