import { flushSync } from "react-dom";
import { prefersReducedMotion } from "./reducedMotion";

/** The part of a same-document `ViewTransition` this module drives. */
export type ViewTransitionHandle = {
  finished: Promise<unknown>;
  updateCallbackDone: Promise<unknown>;
  skipTransition: () => void;
};

/** `document.startViewTransition`, or null where the API is missing. */
export type StartViewTransition = (update: () => void) => ViewTransitionHandle;

/**
 * How a view change is shown:
 * - `shared`: named elements morph between the two views, the rest crossfades;
 * - `crossfade`: reduced motion — a short plain crossfade, nothing moves
 *   (the `prefers-reduced-motion` block in styles.css shortens it to 140ms);
 * - `none`: no View Transitions API, the change is instant.
 */
export type ViewTransitionMode = "shared" | "crossfade" | "none";

/** Picks the mode from API support and the reduced-motion preference. */
export function viewTransitionMode({ supported, reducedMotion }: { supported: boolean; reducedMotion: boolean }): ViewTransitionMode {
  if (!supported) return "none";
  return reducedMotion ? "crossfade" : "shared";
}

/** The attribute marking elements this module named, so they can all be cleared again. */
const namedAttribute = "data-view-transition-named";

/** Gives one element a `view-transition-name` for the next snapshot. */
export function nameViewTransitionElement(element: Element | null, name: string): void {
  if (!(element instanceof HTMLElement)) return;
  element.style.viewTransitionName = name;
  element.setAttribute(namedAttribute, "");
}

/** Clears every name this module set; a name must be unique in each snapshot. */
export function clearViewTransitionNames(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>(`[${namedAttribute}]`).forEach((element) => {
    element.style.viewTransitionName = "";
    element.removeAttribute(namedAttribute);
  });
}

type RunViewTransitionOptions = {
  /** Applies the view change; runs synchronously (flushed) inside the transition. */
  update: () => void;
  /** Names the elements of the outgoing view (shared mode only). */
  nameOld?: () => void;
  /** Names the matching elements of the incoming view, right after `update` (shared mode only). */
  nameNew?: () => void;
  /** Test seams; default to the document API and the OS preference. */
  start?: StartViewTransition | null;
  reducedMotion?: boolean;
};

let active: ViewTransitionHandle | null = null;
let clickRedirectInstalled = false;

function documentStart(): StartViewTransition | null {
  if (typeof document === "undefined" || typeof document.startViewTransition !== "function") return null;
  return (update) => document.startViewTransition(update);
}

/**
 * While a document view transition runs, Chromium hit-tests everything to
 * `<html>`, so a click cannot reach the incoming view. Such a click finishes
 * the running transition at once, then is re-dispatched at the same point.
 */
function installClickRedirect(): void {
  if (clickRedirectInstalled || typeof document === "undefined") return;
  clickRedirectInstalled = true;
  document.addEventListener("click", (event) => {
    const running = active;
    if (!running || event.target !== document.documentElement) return;
    const { clientX, clientY } = event;
    running.skipTransition();
    void running.finished.catch(() => undefined).then(() => requestAnimationFrame(() => {
      const target = document.elementFromPoint(clientX, clientY);
      if (target instanceof HTMLElement && target !== document.documentElement) target.click();
    }));
  }, true);
}

/**
 * Runs one view change as a same-document View Transition. A transition still
 * running is skipped to its end first, and names are assigned only after its
 * update has landed, so two transitions never share a named element. Without
 * the API the update simply runs; under reduced motion nothing is named and
 * the change is a short crossfade. Resolves once the transition has finished.
 */
export async function runViewTransition({ update, nameOld, nameNew, start = documentStart(), reducedMotion = prefersReducedMotion() }: RunViewTransitionOptions): Promise<void> {
  const mode = viewTransitionMode({ supported: Boolean(start), reducedMotion });
  if (active) {
    active.skipTransition();
    await active.updateCallbackDone.catch(() => undefined);
  }
  if (!start || mode === "none") {
    update();
    return;
  }
  const shared = mode === "shared";
  clearViewTransitionNames();
  if (shared) nameOld?.();
  const transition = start(() => {
    clearViewTransitionNames();
    flushSync(update);
    if (shared) nameNew?.();
  });
  active = transition;
  installClickRedirect();
  try {
    // Resolves when a skipped transition jumps to its end; rejects only when `update` threw.
    await transition.finished;
  } finally {
    if (active === transition) {
      active = null;
      clearViewTransitionNames();
    }
  }
}
